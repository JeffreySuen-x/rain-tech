import sqlite3
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import check_password_hash
from server.app import SCHEMA, generate_password_hash
from server.account_recovery import recover_owner_access


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.sqlite3'
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.executescript(SCHEMA)
        self.db.executemany('INSERT INTO users VALUES(?,?,?)', [('a','alice',generate_password_hash('old-password-123')),('b','bob',generate_password_hash('other-password-123'))])
        self.db.executemany('INSERT INTO workspaces VALUES(?,?,?)',[('w','a','synthetic'),('other','b','other')])
        self.db.executemany('INSERT INTO sessions VALUES(?,?,?,?)',[('sa','a','csrf',9999999999),('sb','b','csrf',9999999999)])
    def dump(self):
        return '\n'.join(self.db.iterdump())
    def test_recovery_preserves_other_credentials_and_business(self):
        other=self.db.execute("SELECT * FROM users WHERE id='b'").fetchone()
        business=self.db.execute('SELECT * FROM workspaces ORDER BY id').fetchall()
        recover_owner_access(self.path,'w','a','new-password-123')
        hashed=self.db.execute("SELECT password FROM users WHERE id='a'").fetchone()[0]
        self.assertTrue(check_password_hash(hashed,'new-password-123'))
        self.assertFalse(check_password_hash(hashed,'old-password-123'))
        self.assertEqual(self.db.execute('SELECT id FROM sessions').fetchall(),[('sb',)])
        self.assertEqual(self.db.execute("SELECT * FROM users WHERE id='b'").fetchone(),other)
        self.assertEqual(self.db.execute('SELECT * FROM workspaces ORDER BY id').fetchall(),business)
    def test_invalid_targets_and_password_leave_no_change(self):
        before=self.dump()
        for w,u,p in [('missing','a','long-password-123'),('w','b','long-password-123'),('w','missing','long-password-123'),('w','a','short'),('w','a','x'*1025)]:
            with self.assertRaises(ValueError):recover_owner_access(self.path,w,u,p)
            self.assertEqual(self.dump(),before)
    def test_session_deletion_failure_rolls_password_back(self):
        self.db.execute("CREATE TRIGGER block_recovery BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):recover_owner_access(self.path,'w','a','new-password-123')
        self.assertEqual(self.dump(),before)
