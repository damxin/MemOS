#!/usr/bin/env python3
"""
OpenClaw 记忆迁移工具 - 将 OpenClaw 的 SQLite 记忆数据库迁移到 MemOS

用法:
    python migrate_openclaw_to_memos.py [options]

选项:
    --source PATH       OpenClaw memory SQLite 数据库路径 (默认：/root/.openclaw/memory/main.sqlite)
    --memos-url URL     MemOS API 地址 (默认：http://100.103.37.32:8000)
    --api-key KEY       MemOS API Key
    --user-id ID        MemOS 用户 ID (默认：openclaw-migrated)
    --cube-name NAME    目标知识库名称 (默认：OpenClaw Memories)
    --batch-size N      每批次迁移的记忆数量 (默认：50)
    --dry-run           仅预览，不实际迁移
    --limit N           仅迁移前 N 条记忆 (用于测试)
"""

import sqlite3
import json
import requests
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys


class OpenClawMemoryReader:
    """读取 OpenClaw SQLite 记忆数据库"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
    
    def get_chunks(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取所有记忆片段"""
        query = """
        SELECT id, path, source, start_line, end_line, hash, model, text, embedding, updated_at
        FROM chunks
        ORDER BY updated_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cursor = self.conn.cursor()
        cursor.execute(query)
        
        chunks = []
        for row in cursor.fetchall():
            chunks.append({
                'id': row['id'],
                'path': row['path'],
                'source': row['source'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'hash': row['hash'],
                'model': row['model'],
                'text': row['text'],
                'embedding': json.loads(row['embedding']) if row['embedding'] else None,
                'updated_at': datetime.fromtimestamp(row['updated_at'] / 1000).isoformat() if row['updated_at'] else None
            })
        
        return chunks
    
    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        cursor = self.conn.cursor()
        
        # 总记忆数
        cursor.execute("SELECT COUNT(*) as count FROM chunks")
        total_count = cursor.fetchone()['count']
        
        # 按来源统计
        cursor.execute("SELECT source, COUNT(*) as count FROM chunks GROUP BY source")
        by_source = {row['source']: row['count'] for row in cursor.fetchall()}
        
        # 按模型统计
        cursor.execute("SELECT model, COUNT(*) as count FROM chunks GROUP BY model")
        by_model = {row['model']: row['count'] for row in cursor.fetchall()}
        
        # 最新更新时间
        cursor.execute("SELECT MAX(updated_at) as latest FROM chunks")
        latest = cursor.fetchone()['latest']
        latest_date = datetime.fromtimestamp(latest / 1000).isoformat() if latest else None
        
        return {
            'total_count': total_count,
            'by_source': by_source,
            'by_model': by_model,
            'latest_update': latest_date,
            'db_path': self.db_path
        }
    
    def close(self):
        """关闭数据库连接"""
        self.conn.close()


class MemOSMemoryWriter:
    """写入记忆到 MemOS"""
    
    def __init__(self, base_url: str, api_key: str, user_id: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.user_id = user_id
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    def test_connection(self) -> bool:
        """测试连接"""
        url = f"{self.base_url}/admin/health"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def add_memory(self, text: str, tags: List[str] = None, 
                   metadata: Optional[Dict] = None) -> bool:
        """添加单条记忆"""
        url = f"{self.base_url}/product/add"
        payload = {
            'user_id': self.user_id,
            'content': text,
            'tags': tags or ['openclaw', 'migrated'],
            'metadata': metadata or {}
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            if response.status_code in [200, 201]:
                return True
            else:
                print(f"API 错误：{response.status_code} - {response.text[:200]}")
                return False
        except Exception as e:
            print(f"  添加记忆失败：{e}")
            return False
    
    def add_memory_batch(self, memories: List[Dict], tags_prefix: str = None) -> int:
        """批量添加记忆"""
        success_count = 0
        for memory in memories:
            tags = ['openclaw', 'migrated', memory.get('source', 'memory')]
            if tags_prefix:
                tags.insert(0, tags_prefix)
            
            if self.add_memory(
                text=memory['text'],
                tags=tags,
                metadata={
                    'original_id': memory['id'],
                    'original_path': memory['path'],
                    'migrated_at': datetime.now().isoformat(),
                    'embedding_model': memory.get('model')
                }
            ):
                success_count += 1
        return success_count


def migrate(source_db: str, memos_url: str, api_key: str, user_id: str, 
            batch_size: int, dry_run: bool, limit: Optional[int] = None, tags_prefix: str = None):
    """执行迁移"""
    
    print("=" * 60)
    print("OpenClaw → MemOS 记忆迁移工具")
    print("=" * 60)
    
    # 1. 读取 OpenClaw 记忆
    print(f"\n[1/4] 读取 OpenClaw 记忆数据库：{source_db}")
    reader = OpenClawMemoryReader(source_db)
    stats = reader.get_stats()
    
    print(f"  总记忆数：{stats['total_count']}")
    print(f"  按来源：{stats['by_source']}")
    print(f"  按模型：{stats['by_model']}")
    print(f"  最新时间：{stats['latest_update']}")
    
    if limit:
        print(f"  限制迁移：{limit} 条")
    
    if dry_run:
        print("\n  [DRY RUN] 仅预览，不执行实际迁移")
        chunks = reader.get_chunks(limit=limit or 5)
        print(f"\n  预览前 {len(chunks)} 条记忆:")
        for i, chunk in enumerate(chunks, 1):
            text_preview = chunk['text'][:100].replace('\n', ' ') + "..." if len(chunk['text']) > 100 else chunk['text']
            print(f"  {i}. [{chunk['path']}] {text_preview}")
        reader.close()
        return
    
    # 2. 获取记忆数据
    print(f"\n[2/4] 获取记忆数据...")
    chunks = reader.get_chunks(limit=limit)
    print(f"  获取到 {len(chunks)} 条记忆")
    
    # 3. 连接 MemOS
    print(f"\n[3/4] 连接 MemOS：{memos_url}")
    writer = MemOSMemoryWriter(memos_url, api_key, user_id)
    
    # 测试连接
    if not writer.test_connection():
        print("  ✗ 无法连接到 MemOS，请检查 API Key 和 URL")
        reader.close()
        return
    print("  ✓ 连接成功")
    
    # 4. 迁移记忆
    print(f"\n[4/4] 开始迁移记忆...")
    print(f"  批次大小：{batch_size}")
    print(f"  总批次：{(len(chunks) + batch_size - 1) // batch_size}")
    
    total_success = 0
    total_failed = 0
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        
        # 显示进度
        progress = f"[{batch_num}/{(len(chunks) + batch_size - 1) // batch_size}]"
        print(f"  {progress} 处理批次 {i+1}-{min(i+batch_size, len(chunks))}...", end=" ")
        
        success = writer.add_memory_batch(batch, tags_prefix=tags_prefix)
        total_success += success
        total_failed += len(batch) - success
        
        print(f"成功 {success}/{len(batch)}")
    
    # 完成
    reader.close()
    
    print("\n" + "=" * 60)
    print("迁移完成!")
    print(f"  成功：{total_success} 条")
    print(f"  失败：{total_failed} 条")
    print(f"  成功率：{total_success / len(chunks) * 100:.1f}%")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='OpenClaw 记忆迁移到 MemOS')
    parser.add_argument('--source', default='/root/.openclaw/memory/main.sqlite',
                       help='OpenClaw SQLite 数据库路径')
    parser.add_argument('--memos-url', default='http://100.103.37.32:8000',
                       help='MemOS API 地址')
    parser.add_argument('--api-key', required=True,
                       help='MemOS API Key')
    parser.add_argument('--user-id', default='openclaw-migrated',
                       help='MemOS 用户 ID')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='每批次迁移数量')
    parser.add_argument('--dry-run', action='store_true',
                       help='仅预览，不实际迁移')
    parser.add_argument('--limit', type=int,
                       help='仅迁移前 N 条记忆')
    parser.add_argument('--tags-prefix', default=None,
                       help='标签前缀')
    
    args = parser.parse_args()
    
    try:
        migrate(
            source_db=args.source,
            memos_url=args.memos_url,
            api_key=args.api_key,
            user_id=args.user_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            limit=args.limit,
            tags_prefix=args.tags_prefix
        )
    except KeyboardInterrupt:
        print("\n\n迁移已中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 迁移失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
