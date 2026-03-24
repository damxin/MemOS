#!/usr/bin/env python3
"""
Test runner for MemOS tests.
"""

import unittest
import sys

# Add src to path
sys.path.insert(0, 'src')

# Import test modules
from tests import test_hybrid_search, test_mem_task

# Create test suite
loader = unittest.TestLoader()
suite = unittest.TestSuite()

# Add test suites
suite.addTests(loader.loadTestsFromModule(test_hybrid_search))
suite.addTests(loader.loadTestsFromModule(test_mem_task))

# Run tests
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

# Exit with appropriate code
sys.exit(0 if result.wasSuccessful() else 1)
