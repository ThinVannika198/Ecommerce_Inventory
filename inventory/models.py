# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
# This is an auto-generated Django model module for your inventory database.
from django.db import models
from django.contrib.auth.models import User


class Job(models.Model):
    job_id = models.IntegerField(primary_key=True)
    job_title = models.CharField(max_length=100)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'jobs'
        managed = False
    def __str__(self):
        return self.job_title
    

class Employee(models.Model):
    employeeid = models.IntegerField(primary_key=True)
    employeename = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, null=True, blank=True)
    birthdate = models.DateField(null=True, blank=True)
    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, db_column='job_id')
    address = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table ='employees'
        managed = False
    def __str__(self):
        return self.employeename

class ClientType(models.Model):
    client_type = models.IntegerField(primary_key=True)
    type_name = models.CharField(max_length=50)
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    class Meta:
        db_table = 'client_type'
        managed = False
    def __str__(self):
        return self.type_name

class Client(models.Model):
    client_no = models.IntegerField(primary_key=True)
    clientname = models.CharField(max_length=100)
    address = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    client_type = models.ForeignKey(ClientType, on_delete=models.SET_NULL, null=True, db_column='client_type')
    discount = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    class Meta:
            db_table = 'clients'
    def __str__(self):
        return self.clientname

class ProductType(models.Model):
    producttype_id = models.IntegerField(primary_key=True, db_column='producttype_id')
    producttypename = models.CharField(max_length=150, db_column='producttype_name')  # <--- Matches database column
    remarks = models.TextField(null=True, blank=True, db_column='remarks')
    photo = models.ImageField(upload_to='product_images/', blank=True, null=True, db_column='photo')
    class Meta:
        db_table = 'product_type'

    def __str__(self):
        return self.producttypename

class Product(models.Model):
    product_no = models.AutoField(primary_key=True)
    productname = models.CharField(max_length=150)
    producttype = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, db_column='producttype')
    description = models.TextField(blank=True, null=True, db_column='description')
    size = models.CharField(max_length=10, blank=True, null=True, db_column='size')
    gender = models.CharField(max_length=20, blank=True, null=True, db_column='gender')
    profit_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    unit_measure = models.CharField(max_length=50, null=True, blank=True)
    reorder_level = models.IntegerField(null=True, blank=True)
    sell_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, db_column='discount')
    discount_type = models.CharField(max_length=100, blank=True, null=True, db_column='discount_type')
    qty_on_hand = models.IntegerField()
    photo = models.ImageField(upload_to='product_images/', blank=True, null=True)
    class Meta:
        db_table = 'products'
    def __str__(self):
        return self.productname

class Invoice(models.Model):
    invoiceno = models.IntegerField(primary_key=True)
    invoice_date = models.DateTimeField()
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, db_column='client_no')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, db_column='employeeid')
    invoice_status = models.CharField(max_length=50, null=True, blank=True)
    invoicememo = models.TextField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def balance(self):
        return self.total_amount - self.amount_paid
    class Meta:
        db_table = 'invoices'
    def __str__(self):
        return f"Invoice #{self.invoiceno}"

class InvoiceDetail(models.Model):
    
    invoiceno = models.ForeignKey(Invoice, on_delete=models.CASCADE, db_column='invoiceno')
    product_no = models.ForeignKey(Product, on_delete=models.CASCADE, db_column='product_no')
    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'invoice_details'
        managed = False
        unique_together = (('invoiceno', 'product_no'),)

# ═══════════════════════════════════════════════════════════
# SUPPLIER
# ═══════════════════════════════════════════════════════════
class Supplier(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Phase-Out', 'Phase-Out'),
        ('In Onboarding', 'In Onboarding'),
        ('Internal', 'Internal'),
    ]

    CLASSIFICATION_CHOICES = [
        ('Preferred Supplier', 'Preferred Supplier'),
        ('Active Supplier', 'Active Supplier'),
        ('Potential Supplier', 'Potential Supplier'),
        ('Phase-Out', 'Phase-Out'),
    ]

    supplier_no = models.AutoField(primary_key=True)
    suppliername = models.CharField(max_length=150)
    website = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Active')
    risk_score = models.IntegerField(null=True, blank=True)
    classification = models.CharField(max_length=50, choices=CLASSIFICATION_CHOICES, default='Active Supplier')
    logo = models.ImageField(upload_to='supplier_logos/', blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'suppliers'
        ordering = ['suppliername']

    def __str__(self):
        return self.suppliername


# ═══════════════════════════════════════════════════════════
# PURCHASE (order placed with a supplier)
# ═══════════════════════════════════════════════════════════
class Purchase(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Received', 'Received'),
        ('Cancelled', 'Cancelled'),
        ('Partial', 'Partial'),
    ]

    purchase_no = models.AutoField(primary_key=True)
    purchase_date = models.DateTimeField(auto_now_add=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='supplier_no',
        related_name='purchases',
    )
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='employeeid',
        related_name='purchases',
    )
    purchase_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    purchasememo = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'purchases'
        ordering = ['-purchase_date']

    def __str__(self):
        return f"Purchase #{self.purchase_no}"


# ═══════════════════════════════════════════════════════════
# PURCHASE_DETAIL (line items inside each purchase)
# ═══════════════════════════════════════════════════════════
class PurchaseDetail(models.Model):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        db_column='purchase_no',
        related_name='details',
    )
    product = models.ForeignKey(
        'Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column='product_no',
        related_name='purchase_lines',
    )
    qty = models.IntegerField(default=1)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'purchase_details'

    @property
    def subtotal(self):
        return self.qty * self.cost_price

    def __str__(self):
        return f"Purchase #{self.purchase_id} — {self.product} x{self.qty}"

class StockAdjustment(models.Model):
    ADJUSTMENT_TYPES = (
        ('ADD', 'Addition (+)'),
        ('SUB', 'Subtraction (-)'),
    )
    
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=3, choices=ADJUSTMENT_TYPES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)
    adjusted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.productname} - {self.adjustment_type} {self.quantity}"


