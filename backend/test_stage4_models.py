"""Persistence smoke tests for Stage 4 automation models."""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import AutomationWorkflow, AutomationRun
from backend.schemas import AutomationWorkflowIn, AuroraChatIn
from pydantic import ValidationError

class Stage4AutomationModelTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
    def tearDown(self):
        self.db.close();self.engine.dispose()
    def test_workflow_schema_rejects_unsupported_trigger(self):
        with self.assertRaises(ValidationError):
            AutomationWorkflowIn(name="Unsafe",trigger_event="arbitrary.webhook",enabled=True)
        chat=AuroraChatIn(messages=[{"role":"user","content":"Hello AURORA"}])
        self.assertFalse(chat.messages[0].role == "system")

    def test_workflow_and_execution_log_persist(self):
        workflow=AutomationWorkflow(name="Notify sales",trigger_event="lead.created",action_type="email_notification",enabled=False)
        self.db.add(workflow);self.db.flush()
        run=AutomationRun(workflow_id=workflow.id,trigger_event="lead.created",entity_type="lead",entity_id="12",status="failed",detail="SMTP unavailable")
        self.db.add(run);self.db.commit()
        saved=self.db.query(AutomationWorkflow).one()
        result=self.db.query(AutomationRun).one()
        self.assertEqual(saved.trigger_event,"lead.created")
        self.assertFalse(saved.enabled)
        self.assertEqual(result.entity_id,"12")
        self.assertEqual(result.status,"failed")

if __name__=="__main__": unittest.main()
