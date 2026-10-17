from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from sales.models import Sale
from customers.models import Customer

class TestSaleCreateView(TestCase):
    def setUp(self):
        self.active_customer = Customer.objects.create(name="Active Customer", is_active=True)
        self.inactive_customer = Customer.objects.create(name="Inactive Customer", is_active=False)

    def test_valid_form_with_active_customer(self):
        # Setup form data with active customer
        form_data = {
            "number": "SALE001",
            "date": "2023-10-05",
            "customer": self.active_customer.pk,
        }
        
        response = self.client.post(reverse("sales:create"), form_data)
        
        # Check that the sale was created and redirected
        self.assertRedirects(response, reverse("sales:list"))
        
        # Ensure a Sale object exists with total 0.00
        sale = Sale.objects.get(number="SALE001")
        self.assertEqual(sale.total, Decimal("0.00"))
        
    def test_valid_form_with_inactive_customer(self):
        # Setup form data with inactive customer
        form_data = {
            "number": "SALE002",
            "date": "2023-10-06",
            "customer": self.inactive_customer.pk,
        }
        
        response = self.client.post(reverse("sales:create"), form_data)
        
        # Check that the sale was not created and form is invalid
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Sale.objects.count(), 0)
        
    def test_valid_form_with_unique_number(self):
        # Setup form data with active customer and a unique number
        form_data = {
            "number": "SALE003",
            "date": "2023-10-07",
            "customer": self.active_customer.pk,
        }
        
        response = self.client.post(reverse("sales:create"), form_data)
        
        # Check that the sale was created and redirected
        self.assertRedirects(response, reverse("sales:list"))
        
        # Ensure a Sale object exists with total 0.00
        sale = Sale.objects.get(number="SALE003")
        self.assertEqual(sale.total, Decimal("0.00"))
        
    def test_valid_form_with_same_number(self):
        # Setup form data with active customer and same number again
        form_data_first = {
            "number": "SALE004",
            "date": "2023-10-08",
            "customer": self.active_customer.pk,
        }
        
        # First submission
        response_first = self.client.post(reverse("sales:create"), form_data_first)
        self.assertRedirects(response_first, reverse("sales:list"))
        
        # Second submission with same number
        form_data_second = {
            "number": "SALE004",
            "date": "2023-10-09",
            "customer": self.active_customer.pk,
        }
        response_second = self.client.post(reverse("sales:create"), form_data_second)
        
        # Check that the second submission is invalid due to duplicate number
        self.assertEqual(response_second.status_code, 200)
        self.assertEqual(Sale.objects.count(), 1)
