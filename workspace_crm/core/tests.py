from django.apps import apps
from django.test import TestCase


class DashboardTests(TestCase):
    def test_dashboard_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_every_module_is_listed(self):
        response = self.client.get("/")
        for cfg in apps.get_app_configs():
            if getattr(cfg, "crud_module", False):
                self.assertContains(response, cfg.verbose_name)
