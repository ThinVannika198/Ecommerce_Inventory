from django import forms
from .models import ProductType, Product, Supplier,StockAdjustment

class ProductTypeForm(forms.ModelForm):
    class Meta:
        model = ProductType
        fields = ['producttypename', 'remarks', 'photo']


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            
            'productname',
            'producttype',
            'description',
            'size',
            'gender',
            'profit_percent',
            'unit_measure',
            'reorder_level',
            'sell_price',
            'cost_price',
            'discount',
            'discount_type',
            'qty_on_hand',
            'photo',
        ]




class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'suppliername',
            'website',
            'status',
            'risk_score',
            'classification',
            'logo',
            'contact_email',
            'phone',
            'address',
            'remarks',
        ]

class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['product', 'adjustment_type', 'quantity', 'reason']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'adjustment_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Damaged goods, Stock count correction'}),
        }