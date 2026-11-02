"""Regression tests for the Stage 8 correction pass."""
import pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class DependencyPinTests(unittest.TestCase):
    def test_bcrypt_is_pinned_for_passlib(self):
        # passlib 1.7.4 fails at first password hash with bcrypt>=5; the pin keeps login working.
        lines = (ROOT / "requirements.txt").read_text().splitlines()
        self.assertIn("bcrypt==4.0.1", lines)


class SchemaValidationTests(unittest.TestCase):
    def test_project_progress_and_status_are_bounded(self):
        from pydantic import ValidationError
        from backend.schemas import ProjectIn, ProjectUpdate
        with self.assertRaises(ValidationError): ProjectIn(client_id=1, title="Site", progress=101)
        with self.assertRaises(ValidationError): ProjectUpdate(status="Whatever")
        self.assertEqual(ProjectUpdate(status="In progress", progress=40).progress, 40)

    def test_invoice_currency_is_restricted(self):
        from pydantic import ValidationError
        from backend.schemas import InvoiceIn
        with self.assertRaises(ValidationError): InvoiceIn(client_id=1, number="A1", amount=10, currency="XXX")
        self.assertEqual(InvoiceIn(client_id=1, number="A1", amount=10, currency="USD").currency, "USD")

    def test_career_application_requires_valid_email(self):
        from pydantic import ValidationError
        from backend.schemas import CareerApplicationIn
        with self.assertRaises(ValidationError): CareerApplicationIn(name="Ann", email="not-an-email", role="Engineer")

    def test_article_slug_must_be_url_safe(self):
        from pydantic import ValidationError
        from backend.schemas import ArticleIn
        with self.assertRaises(ValidationError): ArticleIn(title="Hello", slug="Not A Slug")
        self.assertEqual(ArticleIn(title="Hello", slug="hello-world").slug, "hello-world")

    def test_ticket_update_status_is_restricted(self):
        from pydantic import ValidationError
        from backend.schemas import TicketUpdate
        with self.assertRaises(ValidationError): TicketUpdate(status="deleted")


class RolePermissionTests(unittest.TestCase):
    def test_roles_cover_the_admin_tabs_they_can_see(self):
        import os
        os.environ.setdefault("SECRET_KEY", "x" * 40)
        from backend.security import ROLE_PERMISSIONS
        # Licences tab loads customers and products; Careers tab needs careers.view.
        self.assertIn("products.view", ROLE_PERMISSIONS["finance_manager"])
        self.assertIn("careers.view", ROLE_PERMISSIONS["operations_manager"])


if __name__ == "__main__":
    unittest.main()
