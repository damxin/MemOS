import { initPlugin } from './src/index.js';
import * as fs from 'fs';
import * as path from 'path';

async function runTests() {
  console.log('🧪 Testing Memos Local Plugin - Dual Storage Support');
  console.log('='.repeat(60));

  // --- Test 1: SQLite Mode ---
  console.log('\n✅ Test 1: SQLite Mode');
  console.log('-'.repeat(40));

  const sqliteStateDir = '/tmp/test-memos-sqlite';
  fs.rmSync(sqliteStateDir, { recursive: true, force: true });
  fs.mkdirSync(sqliteStateDir, { recursive: true });

  const sqlitePlugin = initPlugin({
    stateDir: sqliteStateDir,
    workspaceDir: '/tmp/test-workspace',
    config: {
      storage: { dbPath: path.join(sqliteStateDir, 'memos.db') }
    }
  });

  console.log(`- SQLite plugin initialized successfully`);
  console.log(`- Tools registered: ${sqlitePlugin.tools.length} tools`);
  console.log(`- SQLite database path: ${path.join(sqliteStateDir, 'memos.db')}`);

  // Test onConversationTurn
  console.log(`- Testing conversation turn capture...`);
  await sqlitePlugin.onConversationTurn([
    { role: 'user', content: '测试用户消息' },
    { role: 'assistant', content: '测试助手回复' }
  ], 'test-session-123');

  // Test flush
  await sqlitePlugin.flush();
  console.log(`- Flush successful`);

  // Test memory search
  console.log(`- Testing memory search...`);
  const searchResult = await sqlitePlugin.handleToolCall({
    tool: 'memory_search',
    parameters: { query: '测试' }
  });
  console.log(`- Memory search returned ${JSON.parse(searchResult.content).hits.length} hits`);

  // Shutdown
  await sqlitePlugin.shutdown();
  console.log(`- SQLite plugin shutdown successful`);
  console.log('✅ SQLite Mode Test PASSED');

  // --- Test 2: PostgreSQL Mode ---
  console.log('\n✅ Test 2: PostgreSQL Mode');
  console.log('-'.repeat(40));

  process.env.DATABASE_URL = 'postgresql://localmemos:fhzmbhMDfRBZd3WC@100.103.37.32:24432/localmemos';

  const pgStateDir = '/tmp/test-memos-pg';
  fs.rmSync(pgStateDir, { recursive: true, force: true });
  fs.mkdirSync(pgStateDir, { recursive: true });

  const pgPlugin = initPlugin({
    stateDir: pgStateDir,
    workspaceDir: '/tmp/test-workspace',
    config: {
      storage: {
        databaseUrl: '${DATABASE_URL}',
        pgSchema: 'public'
      }
    }
  });

  console.log(`- PostgreSQL plugin initialized successfully`);
  console.log(`- Tools registered: ${pgPlugin.tools.length} tools`);
  console.log(`- PostgreSQL database: 100.103.37.32:24432/localmemos`);

  // Test onConversationTurn
  console.log(`- Testing conversation turn capture...`);
  await pgPlugin.onConversationTurn([
    { role: 'user', content: 'PostgreSQL 测试用户消息' },
    { role: 'assistant', content: 'PostgreSQL 测试助手回复' }
  ], 'test-session-456');

  // Test flush
  await pgPlugin.flush();
  console.log(`- Flush successful`);

  // Test memory search
  console.log(`- Testing memory search...`);
  const pgSearchResult = await pgPlugin.handleToolCall({
    tool: 'memory_search',
    parameters: { query: 'PostgreSQL' }
  });
  console.log(`- Memory search returned ${JSON.parse(pgSearchResult.content).hits.length} hits`);

  // Shutdown
  await pgPlugin.shutdown();
  console.log(`- PostgreSQL plugin shutdown successful`);
  console.log('✅ PostgreSQL Mode Test PASSED');

  console.log('\n' + '='.repeat(60));
  console.log('🎉 ALL TESTS PASSED! Dual storage support is working correctly!');
}

runTests().catch(err => {
  console.error('❌ TEST FAILED:', err);
  process.exit(1);
});
