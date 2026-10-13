from django.test import TestCase
from decimal import Decimal
from customers.models import Customer
from sales.models import Sale

class TestCustomerTotalSpent(TestCase):
    def test_customer_with_no_sales_has_total_spent_zero(self):
        customer = Customer.objects.create(name="John Doe", email="john@example.com", phone="123456789")
        self.assertEqual(customer.total_spent(), Decimal("0.00"))

    def test_customer_with_one_sale_has_total_spent_equal_to_sale_total(self):
        customer = Customer.objects.create(name="Jane Doe", email="jane@example.com", phone="987654321")
        sale = Sale.objects.create(number="S001", date="2023-01-01", customer=customer, total=Decimal("100.00"))
        self.assertEqual(customer.total_spent(), Decimal("100.00"))

    def test_customer_with_multiple_sales_has_total_spent_equal_to_sum_of_sale_totals(self):
        customer = Customer.objects.create(name="Alice Smith", email="alice@example.com", phone="123456789")
        sale1 = Sale.objects.create(number="S002", date="2023-01-01", customer=customer, total=Decimal("50.00"))
        sale2 = Sale.objects.create(number="S003", date="2023-01-02", customer=customer, total=Decimal("75.00"))
        self.assertEqual(customer.total_spent(), Decimal("125.00"))

    def test_other_customers_sales_are_not_counted(self):
        customer = Customer.objects.create(name="Bob Lee", email="bob@example.com", phone="111111111")
        other = Customer.objects.create(name="Carl Roe", email="carl@example.com", phone="222222222")
        Sale.objects.create(number="S010", date="2023-02-01", customer=customer, total=Decimal("40.00"))
        Sale.objects.create(number="S011", date="2023-02-02", customer=other, total=Decimal("900.00"))
        self.assertEqual(customer.total_spent(), Decimal("40.00"))
        self.assertEqual(other.total_spent(), Decimal("900.00"))
