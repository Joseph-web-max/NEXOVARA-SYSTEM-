"""Smoke tests for Stage 3 additive business-operations tables."""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import Quote, AuditLog

class Stage3ModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_quote_request_persists_and_defaults_to_new(self):
        quote = Quote(name="Test Client", email="client@example.com", service="Web platform", details="A test request")
        self.db.add(quote)
        self.db.commit()
        saved = self.db.query(Quote).one()
        self.assertEqual(saved.status, "new")
        self.assertEqual(saved.email, "client@example.com")

    def test_audit_log_persists_action_and_entity(self):
        event = AuditLog(actor_email="admin@example.com", action="quote.updated", entity_type="quote", entity_id="7", details='{"status":"quoted"}')
        self.db.add(event)
        self.db.commit()
        saved = self.db.query(AuditLog).one()
        self.assertEqual(saved.action, "quote.updated")
        self.assertEqual(saved.entity_id, "7")

if __name__ == "__main__":
    unittest.main()
