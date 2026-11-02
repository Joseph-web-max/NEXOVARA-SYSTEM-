import unittest
from backend.database import normalize_database_url
from backend.models import User, Payment, PaymentEvent, StoredFile, PasswordResetToken

class ProductionInfrastructureTests(unittest.TestCase):
    def test_supabase_transaction_pooler_is_normalized(self):
        url, transaction = normalize_database_url("postgresql://postgres.project:pw@aws-0-region.pooler.supabase.com:6543/postgres")
        self.assertTrue(url.startswith("postgresql+psycopg://"))
        self.assertIn("sslmode=require", url)
        self.assertTrue(transaction)

    def test_supabase_session_pooler_is_not_transaction_mode(self):
        url, transaction = normalize_database_url("postgres://postgres.project:pw@aws-0-region.pooler.supabase.com:5432/postgres")
        self.assertTrue(url.startswith("postgresql+psycopg://"))
        self.assertFalse(transaction)

    def test_local_sqlite_remains_supported(self):
        url, transaction = normalize_database_url("sqlite:///./test.db")
        self.assertEqual(url, "sqlite:///./test.db")
        self.assertFalse(transaction)

    def test_production_tables_are_registered(self):
        for model in (User, Payment, PaymentEvent, StoredFile, PasswordResetToken):
            self.assertIn(model.__tablename__, model.metadata.tables)
        self.assertIn("mfa_enabled", User.__table__.columns)
        self.assertIn("token_version", User.__table__.columns)

if __name__ == "__main__": unittest.main()
