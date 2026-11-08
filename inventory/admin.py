from django.contrib import admin
from .models import (
    Job, Employee, ClientType, Client,
    ProductType, Product, Invoice, InvoiceDetail,
    Supplier, Purchase, PurchaseDetail,
)

admin.site.register(Job)
admin.site.register(Employee)
admin.site.register(ClientType)
admin.site.register(Client)
admin.site.register(ProductType)
admin.site.register(Product)
admin.site.register(Invoice)
admin.site.register(InvoiceDetail)

# Supplier — simple register is enough
admin.site.register(Supplier)


# Purchase — needs inline
class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail
    extra = 1


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('purchase_no', 'purchase_date', 'supplier', 'purchase_status', 'total_amount')
    inlines = [PurchaseDetailInline]


admin.site.register(PurchaseDetail)