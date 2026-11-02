"""Persistence tests for global platform services."""
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import User, Product, License, Notification, PartnerApplication

class GlobalPlatformModelTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.user=User(name="Test User",email="user@example.com",password_hash="test-hash",role="client")
        self.product=Product(name="Test Product",slug="test-product",status="draft")
        self.db.add_all([self.user,self.product]);self.db.commit()
    def tearDown(self):
        self.db.close();self.engine.dispose()
    def test_license_is_assigned_to_customer(self):
        row=License(client_id=self.user.id,product_id=self.product.id,license_key="NXV-test-key",status="active",seats=3)
        self.db.add(row);self.db.commit()
        saved=self.db.query(License).one()
        self.assertEqual(saved.client_id,self.user.id);self.assertEqual(saved.seats,3)
    def test_notification_belongs_to_user(self):
        self.db.add(Notification(user_id=self.user.id,title="Project update",body="A milestone changed"));self.db.commit()
        self.assertEqual(self.db.query(Notification).one().user_id,self.user.id)
    def test_partner_application_defaults_to_new(self):
        self.db.add(PartnerApplication(name="Partner Contact",email="partner@example.com",organization="Example"));self.db.commit()
        self.assertEqual(self.db.query(PartnerApplication).one().status,"new")
if __name__=="__main__": unittest.main()
