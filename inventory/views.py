import json
import re
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from urllib.parse import quote, urlparse

from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth import aauthenticate, alogin, alogout
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Case, Count, DecimalField, F, Max, Q, Sum, When
from django.db.models.functions import Coalesce, TruncMonth
from django.http import JsonResponse
from django.shortcuts import aget_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .form import ProductForm, ProductTypeForm, SupplierForm
from .models import (
    Client, ClientType, Employee, Invoice, InvoiceDetail, Job, Product,
    ProductType, Purchase, PurchaseDetail, Supplier,
)

MONEY = DecimalField(max_digits=12, decimal_places=2)
SALES_TARGET = 4000


# ═════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════
def in_thread(fn):
    """Run a sync function (transactions, raw SQL, forms) without blocking."""
    return sync_to_async(fn, thread_sensitive=True)()


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _safe_next(request, default):
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})
    return nxt if ok and nxt else default


async def user_ctx(request):
    u = await request.auser()
    return {
        'me': u,
        'user_is_authenticated': u.is_authenticated,
        'user_username': u.get_username(),
        'user_is_superuser': u.is_superuser,
    }


async def get_cart(request):
    return await request.session.aget('cart', {})


async def save_cart(request, cart):
    await request.session.aset('cart', cart)


# ═════════════════════════════════════════════════════════════
# Access control
# ═════════════════════════════════════════════════════════════
def admin_required(view):
    @wraps(view)
    async def wrapper(request, *args, **kwargs):
        user = await request.auser()
        if not user.is_authenticated:
            return redirect('login_admin')
        if not user.is_superuser:
            await alogout(request)
            messages.error(request, "You have been logged out. Admin privileges required.")
            return redirect('login_admin')
        return await view(request, *args, **kwargs)
    return wrapper


def staff_required(view):
    @wraps(view)
    async def wrapper(request, *args, **kwargs):
        user = await request.auser()
        if not user.is_authenticated:
            return redirect('login_admin')
        if not user.is_staff:
            messages.error(request, "You do not have permission to access this page.")
            return redirect('login_admin')
        return await view(request, *args, **kwargs)
    return wrapper


def login_required_async(view):
    @wraps(view)
    async def wrapper(request, *args, **kwargs):
        user = await request.auser()
        if user.is_authenticated:
            return await view(request, *args, **kwargs)
        if request.method == 'POST':
            back = urlparse(request.META.get('HTTP_REFERER', '')).path or '/'
        else:
            back = request.get_full_path()
        messages.info(request, "Please sign in to continue.")
        return redirect(f"{reverse('login')}?next={quote(back)}")
    return wrapper


# ═════════════════════════════════════════════════════════════
# Dashboard
# ═════════════════════════════════════════════════════════════
def _month_start(today, back):
    y, m = today.year, today.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


async def _monthly_data(months=6):
    today = timezone.localdate()
    start = _month_start(today, months - 1)

    sales_rows = (Invoice.objects.filter(invoice_date__date__gte=start)
                  .annotate(m=TruncMonth('invoice_date')).values('m')
                  .annotate(total=Sum('total_amount')))
    purchase_rows = (Purchase.objects.exclude(purchase_status='Cancelled')
                     .filter(purchase_date__date__gte=start)
                     .annotate(m=TruncMonth('purchase_date')).values('m')
                     .annotate(total=Sum('total_amount')))

    sales = {r['m'].strftime('%Y-%m'): float(r['total'] or 0) async for r in sales_rows}
    purchases = {r['m'].strftime('%Y-%m'): float(r['total'] or 0) async for r in purchase_rows}

    keys, labels = [], []
    for i in range(months - 1, -1, -1):
        d = _month_start(today, i)
        keys.append(d.strftime('%Y-%m'))
        labels.append(d.strftime('%b'))

    return {
        'keys': keys,
        'labels': labels,
        'target': [SALES_TARGET] * months,
        'sales': [sales.get(k, 0) for k in keys],
        'purchases': [purchases.get(k, 0) for k in keys],
    }


async def month_customers_view(request):
    try:
        year, month = [int(x) for x in request.GET.get('month', '').split('-')]
    except ValueError:
        return JsonResponse({'error': 'Invalid month.'}, status=400)

    inv = Invoice.objects.filter(invoice_date__year=year, invoice_date__month=month)
    rows = (inv.filter(client__isnull=False)
            .values('client_id', 'client__clientname')
            .annotate(orders=Count('invoiceno'), spent=Sum('total_amount'))
            .order_by('-spent'))
    customers = [
        {'name': r['client__clientname'], 'orders': r['orders'], 'spent': float(r['spent'] or 0)}
        async for r in rows
    ]
    total = (await inv.aaggregate(t=Sum('total_amount')))['t'] or 0

    return JsonResponse({
        'month': date(year, month, 1).strftime('%B %Y'),
        'customers_count': len(customers),
        'walkins': await inv.filter(client__isnull=True).acount(),
        'orders': await inv.acount(),
        'sales': float(total),
        'customers': customers,
    })


@admin_required
async def dashboard_view(request):
    qty_price = Sum(F('qty') * F('price'), output_field=MONEY)

    total_sale = (await InvoiceDetail.objects.aaggregate(
        total=Coalesce(qty_price, 0, output_field=MONEY)))['total']

    total_cost = (await Product.objects.aaggregate(
        total=Coalesce(Sum(F('cost_price') * F('qty_on_hand'), output_field=MONEY),
                       0, output_field=MONEY)))['total']

    payment_sent = (await Purchase.objects.filter(
        purchase_status__in=['Received', 'Partial']
    ).aaggregate(total=Coalesce(Sum('total_amount'), 0, output_field=MONEY)))['total']

    payment_received = (await InvoiceDetail.objects.filter(
        invoiceno__invoice_status='Paid'
    ).aaggregate(total=Coalesce(qty_price, 0, output_field=MONEY)))['total']

    low_stock = await Product.objects.filter(
        qty_on_hand__lte=F('reorder_level'), qty_on_hand__gt=0).acount()
    out_of_stock = await Product.objects.filter(qty_on_hand=0).acount()
    total_products = await Product.objects.acount()

    recent_invoices = [
        i async for i in Invoice.objects.select_related('client').order_by('-invoice_date')[:5]
    ]
    brand_data = [
        b async for b in ProductType.objects
        .annotate(total_stock=Sum('product__qty_on_hand'))
        .filter(total_stock__gt=0).order_by('-total_stock')[:8]
    ]

    months = 12 if request.GET.get('months') == '12' else 6
    chart_data = await _monthly_data(months)

    context = {
        'total_sale': total_sale,
        'total_cost': total_cost,
        'payment_sent': payment_sent,
        'payment_received': payment_received,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'total_products': total_products,
        'recent_invoices': recent_invoices,
        'chart_data': chart_data,
        'brand_labels_json': json.dumps([str(b) for b in brand_data]),
        'brand_counts_json': json.dumps([b.total_stock for b in brand_data]),
        **await user_ctx(request),
    }
    return render(request, 'backoffice/dashboard/dashboard.html', context)


# ═════════════════════════════════════════════════════════════
# Shop pages
# ═════════════════════════════════════════════════════════════
async def home_view(request):
    products = [p async for p in Product.objects.all()]
    cart = await get_cart(request)
    return render(request, 'shop/home.html', {
        'products': products, 'cart_count': len(cart), **await user_ctx(request),
    })


async def collection_view(request):
    categories = [c async for c in ProductType.objects.all()]
    qs = Product.objects.all()
    category_id = request.GET.get('category')
    if category_id:
        qs = qs.filter(producttype_id=category_id)
    products = [p async for p in qs]
    cart = await get_cart(request)
    return render(request, 'shop/collection.html', {
        'categories': categories, 'products': products,
        'cart_count': len(cart), **await user_ctx(request),
    })


async def about_view(request):
    cart = await get_cart(request)
    return render(request, 'shop/about.html', {'cart_count': len(cart), **await user_ctx(request)})


async def product_detail_view(request, product_no):
    product = await aget_object_or_404(Product, product_no=product_no)
    cart = await get_cart(request)
    return render(request, 'shop/product_detail.html', {
        'product': product, 'cart_count': len(cart), **await user_ctx(request),
    })


# ═════════════════════════════════════════════════════════════
# Cart
# ═════════════════════════════════════════════════════════════
@login_required_async
async def add_to_cart_view(request, product_no):
    if request.method != 'POST':
        return redirect('product_detail', product_no=product_no)

    product = await aget_object_or_404(Product, product_no=product_no)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 0

    cart = await get_cart(request)
    key = str(product_no)
    already = cart.get(key, {}).get('quantity', 0)

    if quantity < 1:
        messages.error(request, "Invalid quantity.")
        return redirect('product_detail', product_no=product_no)
    if already + quantity > product.qty_on_hand:
        messages.error(request, f"Only {product.qty_on_hand} of {product.productname} in stock.")
        return redirect('product_detail', product_no=product_no)

    if key in cart:
        cart[key]['quantity'] += quantity
    else:
        cart[key] = {'productname': product.productname,
                     'price': float(product.sell_price), 'quantity': quantity}

    await save_cart(request, cart)
    return redirect('product_detail', product_no=product_no)


async def cart_view(request):
    cart = await get_cart(request)
    items, total = [], 0
    for product_no, item in cart.items():
        line = item['price'] * item['quantity']
        total += line
        items.append({'product_no': product_no, 'productname': item['productname'],
                      'price': item['price'], 'quantity': item['quantity'], 'total_price': line})
    return render(request, 'shop/cart.html', {
        'cart_items': items, 'cart_count': len(cart),
        'total_amount': total, **await user_ctx(request),
    })


@login_required_async
async def update_cart_view(request, product_no):
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', 1))
        except ValueError:
            quantity = 1
        cart = await get_cart(request)
        key = str(product_no)
        if key in cart:
            if quantity > 0:
                cart[key]['quantity'] = quantity
            else:
                del cart[key]
            await save_cart(request, cart)
    return redirect('cart_page')


@login_required_async
async def remove_from_cart_view(request, product_no):
    cart = await get_cart(request)
    if cart.pop(str(product_no), None) is not None:
        await save_cart(request, cart)
    return redirect('cart_page')


# ═════════════════════════════════════════════════════════════
# Online checkout  (atomic transaction => one sync block)
# ═════════════════════════════════════════════════════════════
@login_required_async
async def checkout_view(request):
    cart = await get_cart(request)
    if not cart:
        return redirect('cart_page')

    total_amount = sum(i['quantity'] * i['price'] for i in cart.values())
    ctx = {'total_amount': total_amount, 'cart_count': len(cart), 'errors': [], 'form': {}}

    if request.method != 'POST':
        return render(request, 'shop/checkout.html', ctx)

    clientname = (request.POST.get('full_name') or '').strip()
    address = (request.POST.get('shipping_address') or '').strip()
    phone = (request.POST.get('phone_number') or '').strip()
    ctx['form'] = {'full_name': clientname, 'shipping_address': address, 'phone_number': phone}

    if not clientname:
        ctx['errors'].append("Please enter your full name.")
    if not address:
        ctx['errors'].append("Please enter your shipping address.")
    if not phone:
        ctx['errors'].append("Please enter your phone number.")
    if ctx['errors']:
        return render(request, 'checkout.html', ctx)

    def _do_checkout():
        with transaction.atomic():
            for product_no, item in cart.items():
                p = Product.objects.select_for_update().get(product_no=product_no)
                if p.qty_on_hand < int(item['quantity']):
                    raise ValueError(f"Product '{p.productname}' out of stock.")

            client = Client.objects.filter(phone=phone).first()
            if client:
                client.address = address
                if not client.clientname:
                    client.clientname = clientname
                client.save(update_fields=['address', 'clientname'])
            else:
                max_no = Client.objects.aggregate(Max('client_no'))['client_no__max'] or 0
                client = Client.objects.create(client_no=max_no + 1, clientname=clientname,
                                               address=address, phone=phone)

            total = sum(Decimal(str(i['price'])) * int(i['quantity']) for i in cart.values())

            with connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO invoices
                        (invoice_date, client_no, invoice_status, invoicememo, total_amount, amount_paid)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING invoiceno;
                """, [timezone.now(), client.client_no, 'Completed',
                      'Online Web Checkout', total, total])
                invoice_no = cur.fetchone()[0]

            for product_no, item in cart.items():
                with connection.cursor() as cur:
                    cur.execute("""
                        INSERT INTO invoice_details (invoiceno, product_no, qty, price)
                        VALUES (%s, %s, %s, %s)
                    """, [invoice_no, product_no, item['quantity'], item['price']])
                p = Product.objects.get(product_no=product_no)
                p.qty_on_hand -= int(item['quantity'])
                p.save()

    try:
        await in_thread(_do_checkout)
    except ValueError as e:
        ctx['errors'].append(str(e))
        return render(request, 'checkout.html', ctx)

    await save_cart(request, {})
    return redirect('checkout_success')


@login_required_async
async def checkout_success_view(request):
    cart = await get_cart(request)
    return render(request, 'shop/checkout_success.html', {'cart_count': len(cart)})


# ═════════════════════════════════════════════════════════════
# Categories
# ═════════════════════════════════════════════════════════════
@admin_required
async def categories_view(request):
    categories = [c async for c in ProductType.objects.all()]
    return render(request, 'backoffice/catalog/categories.html', {'categories': categories})


async def add_category_view(request):
    if request.method == 'POST':
        max_id = (await ProductType.objects.aaggregate(m=Max('producttype_id')))['m'] or 0
        await ProductType.objects.acreate(
            producttype_id=max_id + 1,
            producttypename=request.POST.get('producttype_name'),
            remarks=request.POST.get('remarks', ''),
            photo=request.FILES.get('photo'),
        )
        return redirect('categories')
    return render(request, 'backoffice/catalog/add_category.html')


async def edit_category_view(request, category_id):
    category = await aget_object_or_404(ProductType, producttype_id=category_id)

    if request.method == 'POST':
        form = ProductTypeForm(request.POST, request.FILES, instance=category)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(form.save)()
            return redirect('categories')
    else:
        form = ProductTypeForm(instance=category)

    return render(request, 'backoffice/catalog/add_category.html', {'form': form, 'category': category})


async def delete_category_view(request, pk):
    category = await aget_object_or_404(ProductType, pk=pk)
    await category.adelete()
    return redirect('categories')


# ═════════════════════════════════════════════════════════════
# Products
# ═════════════════════════════════════════════════════════════
@admin_required
async def products_view(request):
    q = request.GET.get('q', '')
    qs = Product.objects.select_related('producttype').order_by('-product_no')
    if q:
        qs = qs.filter(productname__icontains=q)
    products = [p async for p in qs]
    return render(request, 'backoffice/catalog/products.html', {'products': products})


async def add_product_view(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(form.save)()
            return redirect('products')
    else:
        form = ProductForm()
    categories = [c async for c in ProductType.objects.all()]
    return render(request, 'backoffice/catalog/add_product.html', {'form': form, 'categories': categories})





async def edit_product_view(request, product_no):
    product = await aget_object_or_404(Product, product_no=product_no)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(form.save)()
            return redirect('products')
    else:
        form = ProductForm(instance=product)
    categories = [c async for c in ProductType.objects.all()]
    return render(request, 'backoffice/catalog/edit_product.html',
                  {'form': form, 'product': product, 'categories': categories})


async def delete_product_view(request, product_no):
    product = await aget_object_or_404(Product, product_no=product_no)
    if request.method == 'POST':
        await product.adelete()
        return redirect('products')
    return render(request, 'backoffice/catalog/delete_product.html', {'product': product})


# ═════════════════════════════════════════════════════════════
# Suppliers
# ═════════════════════════════════════════════════════════════
@admin_required
async def suppliers_view(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    tab = request.GET.get('tab', '')

    valid = Q(purchases__purchase_status__in=['Received', 'Partial'])

    qs = Supplier.objects.annotate(
        purchases_count=Count('purchases', filter=valid, distinct=True),
        items_bought=Coalesce(Sum('purchases__details__qty', filter=valid), 0),
        total_spent=Coalesce(
            Sum(F('purchases__details__qty') * F('purchases__details__cost_price'),
                filter=valid, output_field=MONEY),
            0, output_field=MONEY),
    )

    if q:
        qs = qs.filter(suppliername__icontains=q)
    if status:
        qs = qs.filter(status=status)

    if tab == 'top':
        qs = qs.order_by('-items_bought')[:20]   # slice last, after all filters

    suppliers = [s async for s in qs]
    return render(request, 'backoffice/catalog/suppliers.html', {
        'suppliers': suppliers,
        'q': q,
        'current_status': status,
        'current_tab': tab,
    })

async def add_supplier_view(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST, request.FILES)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(form.save)()
            return redirect('suppliers')
    else:
        form = SupplierForm()
    return render(request, 'backoffice/catalog/add_supplier.html', {'form': form})


async def edit_supplier_view(request, supplier_no):
    supplier = await aget_object_or_404(Supplier, supplier_no=supplier_no)
    if request.method == 'POST':
        form = SupplierForm(request.POST, request.FILES, instance=supplier)
        if await sync_to_async(form.is_valid)():
            await sync_to_async(form.save)()
            return redirect('suppliers')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'backoffice/catalog/edit_supplier.html', {'form': form, 'supplier': supplier})


async def delete_supplier_view(request, supplier_no):
    supplier = await aget_object_or_404(Supplier, supplier_no=supplier_no)
    if request.method == 'POST':
        await supplier.adelete()
        return redirect('suppliers')
    return render(request, 'backoffice/catalog/delete_supplier.html', {'supplier': supplier})


# ═════════════════════════════════════════════════════════════
# Stock
# ═════════════════════════════════════════════════════════════
@admin_required
async def stock_management_view(request):
    total_qty = low = out = 0
    rows = []
    async for p in Product.objects.select_related('producttype').order_by('-product_no'):
        qty = p.qty_on_hand or 0
        reorder = p.reorder_level if p.reorder_level is not None else 5
        total_qty += qty
        if qty == 0:
            out += 1
        elif qty <= reorder:
            low += 1

        try:
            photo_url = p.photo.url if p.photo else None
        except Exception:
            photo_url = None

        rows.append({
            'product_no': p.product_no,
            'productname': p.productname,
            'photo_url': photo_url,
            'category': str(p.producttype) if p.producttype_id else 'Uncategorized',
            'qty_on_hand': qty,
            'reorder_level': reorder,
        })

    return render(request, 'backoffice/inventory/stock.html', {
        'products': rows, 'total_qty': total_qty,
        'low_stock_count': low, 'out_of_stock_count': out,
    })


async def stock_adjustment_view(request):
    products = [p async for p in Product.objects.order_by('productname')]

    if request.method == 'POST':
        product_no = request.POST.get('product_no')
        adjustment_type = request.POST.get('adjustment_type')

        def _adjust(qty_change):
            with transaction.atomic():
                try:
                    p = Product.objects.select_for_update().get(product_no=product_no)
                except Product.DoesNotExist:
                    raise ValueError("រកមិនឃើញផលិតផលនេះនៅក្នុងប្រព័ន្ធទេ។")
                if adjustment_type == 'add':
                    p.qty_on_hand += qty_change
                elif adjustment_type == 'subtract':
                    if p.qty_on_hand < qty_change:
                        raise ValueError(f"ស្តុកបច្ចុប្បន្នមានត្រឹមតែ {p.qty_on_hand} មិនអាចកាត់បន្ថយលើសចំនួននេះបានទេ។")
                    p.qty_on_hand -= qty_change
                else:
                    raise ValueError("ប្រភេទនៃការកែតម្រូវមិនត្រឹមត្រូវ។")
                p.save()

        try:
            qty_change = int(request.POST.get('quantity'))
            if qty_change <= 0:
                raise ValueError("បរិមាណកែតម្រូវត្រូវតែជាចំនួនគត់វិជ្ជមានធំជាង 0។")
            await in_thread(lambda: _adjust(qty_change))
            messages.success(request, "កែតម្រូវស្តុកបានដោយជោគជ័យ!")
            return redirect('stock')
        except ValueError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, "មានបញ្ហាកើតឡើងពេលកំពុងកែតម្រូវស្តុក សូមព្យាយាមម្តងទៀត។")

    return render(request, 'backoffice/inventory/stock_adjustment.html', {'products': products})


@admin_required
async def add_purchase_view(request):
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        product_no = request.POST.get('product')
        qty = int(request.POST.get('qty', 0))
        cost = Decimal(request.POST.get('cost', '0.00'))

        def _save():
            with transaction.atomic():
                product = Product.objects.select_for_update().get(product_no=product_no)
                product.qty_on_hand += qty
                product.save()
                max_no = Purchase.objects.aggregate(Max('purchase_no'))['purchase_no__max'] or 0
                purchase = Purchase.objects.create(
                    purchase_no=max_no + 1, supplier_id=supplier_id,
                    purchase_date=timezone.now(), purchase_status='Received',
                    total_amount=cost * qty)
                PurchaseDetail.objects.create(purchase=purchase, product=product,
                                              qty=qty, cost_price=cost)

        await in_thread(_save)
        messages.success(request, "Stock purchased and added successfully!")
        return redirect('stock')

    suppliers = [s async for s in Supplier.objects.all()]
    products = [p async for p in Product.objects.all()]
    return render(request, 'backoffice/inventory/add_purchase.html', {'suppliers': suppliers, 'products': products})


# ═════════════════════════════════════════════════════════════
# Orders
# ═════════════════════════════════════════════════════════════
@staff_required
async def orders_view(request):
    day = _parse_date(request.GET.get('date', '').strip())
    channel = request.GET.get('channel', '')

    qs = Invoice.objects.select_related('client', 'employee').order_by('-invoice_date')
    if day:
        qs = qs.filter(invoice_date__date=day)
    invoices = [i async for i in qs]

    # totals per invoice with the ORM (no raw SQL)
    totals = {
        r['invoiceno']: r['t'] async for r in
        InvoiceDetail.objects.values('invoiceno')
        .annotate(t=Sum(F('qty') * F('price'), output_field=MONEY))
    }

    for inv in invoices:
        inv.computed_total = totals.get(inv.invoiceno, 0)
        inv.in_store = bool(inv.employee_id) or (inv.invoicememo or '').startswith('In-Store')
        inv.cashier_name = inv.employee.employeename if inv.employee else "Unlinked / Admin"

    def summary(rows):
        return {
            'orders': len(rows),
            'clients': len({r.client_id for r in rows if r.client_id}),
            'walkins': sum(1 for r in rows if not r.client_id),
            'sales': sum(r.computed_total for r in rows),
        }

    online = [i for i in invoices if not i.in_store]
    store = [i for i in invoices if i.in_store]
    shown = online if channel == 'online' else store if channel == 'store' else invoices

    return render(request, 'backoffice/sales/orders.html', {
        'orders': shown, 'day': day,
        'day_iso': day.isoformat() if day else '',
        'channel': channel,
        'all_s': summary(invoices), 'online_s': summary(online), 'store_s': summary(store),
        **await user_ctx(request),
    })


async def order_detail_view(request, invoiceno):
    invoice = await aget_object_or_404(
        Invoice.objects.select_related('client', 'employee'), invoiceno=invoiceno)

    items = [
        {'product_no': r['product_no'], 'productname': r['product_no__productname'],
         'qty': r['qty'], 'price': float(r['price']),
         'line_total': float(r['qty'] * r['price'])}
        async for r in InvoiceDetail.objects.filter(invoiceno_id=invoiceno)
        .values('product_no', 'product_no__productname', 'qty', 'price')
    ]

    subtotal = sum(i['line_total'] for i in items)
    total_amount = float(invoice.total_amount or 0)
    discount = max(subtotal - total_amount, 0)
    paid = float(invoice.amount_paid or 0)

    return render(request, 'backoffice/sales/order_detail.html', {
        'order': invoice, 'items': items,
        'subtotal': subtotal, 'discount': discount,
        'balance': total_amount - paid,
        'cashier_name': invoice.employee.employeename if invoice.employee else "Not Recorded",
    })


async def add_payment_view(request, invoiceno):
    if request.method != 'POST':
        return redirect('backoffice/sales/order_detail', invoiceno=invoiceno)

    def _pay():
        try:
            # 1. Get the amount from the form
            amount = Decimal(request.POST.get('amount', '0'))
        except Exception:
            raise ValueError("Invalid amount format.")

        with transaction.atomic():
            # 2. Safely lock and fetch the invoice
            inv = Invoice.objects.select_for_update().get(invoiceno=invoiceno)
            
            # 3. Check if the amount is valid
            if amount <= 0 or amount > inv.balance:
                raise ValueError(f"Enter an amount between 0.01 and {inv.balance:.2f}.")

            # 4. Update the paid amount
            inv.amount_paid += amount
            
            # 5. Set the status cleanly
            if inv.amount_paid >= inv.total_amount:
                inv.invoice_status = 'Paid'
            else:
                inv.invoice_status = 'Partial'
                
            # 6. Save to database
            inv.save(update_fields=['amount_paid', 'invoice_status'])

    try:
        await sync_to_async(_pay, thread_sensitive=True)()
        messages.success(request, "Payment recorded successfully.")
    except ValueError as e:
        messages.error(request, str(e))
    except Invoice.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('orders')
        
    return redirect('order_detail', invoiceno=invoiceno)

# ═════════════════════════════════════════════════════════════
# POS
# ═════════════════════════════════════════════════════════════
@staff_required
async def pos_view(request):
    products = [
        {'product_no': p.product_no, 'name': p.productname,
         'price': float(p.sell_price or 0), 'qty': p.qty_on_hand or 0,
         'photo': p.photo.url if p.photo else ''}
        async for p in Product.objects.order_by('productname')
    ]
    employees = [e async for e in Employee.objects.order_by('employeename')]
    return render(request, 'backoffice/sales/pos.html', {
        'products': products, 'employees': employees, **await user_ctx(request),
    })


async def pos_checkout_view(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST only.'}, status=405)

    user = await request.auser()
    if not (user.is_authenticated and user.is_staff):
        return JsonResponse({'ok': False, 'error': 'Not allowed.'}, status=403)

    try:
        data = json.loads(request.body)
        lines = data.get('items', [])
        payment = data.get('payment_method', 'Cash')
        received = Decimal(str(data.get('received') or 0))
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        allow_debt = bool(data.get('allow_debt'))
        cashier_id = data.get('cashier_id')
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid data.'}, status=400)

    if not lines:
        return JsonResponse({'ok': False, 'error': 'The cart is empty.'}, status=400)
    if not cashier_id:
        return JsonResponse({'ok': False, 'error': 'Please select a cashier.'}, status=400)

    def _do_sale():
        with transaction.atomic():
            total_final = Decimal('0')
            priced = []

            for line in lines:
                qty = int(line['qty'])
                if qty <= 0:
                    raise ValueError("Invalid quantity.")
                product = Product.objects.select_for_update().get(
                    product_no=int(line['product_no']))
                if product.qty_on_hand < qty:
                    raise ValueError(f"Not enough stock for {product.productname} "
                                     f"(only {product.qty_on_hand} left).")
                disc = Decimal(str(line.get('discount') or 0))
                if not (0 <= disc <= 100):
                    raise ValueError("Discount must be between 0 and 100%.")

                original_unit = product.sell_price
                total_final += original_unit * (1 - disc / 100) * qty
                priced.append((product, qty, original_unit))

            paid = total_final
            if payment == 'Cash' and received < total_final:
                if allow_debt:
                    paid = received
                else:
                    raise ValueError("Cash received is less than the total. "
                                     "Tick 'Customer pays the rest later'.")

            client = None
            if phone:
                client = Client.objects.filter(phone=phone).first()
                if not client and name:
                    max_no = Client.objects.aggregate(Max('client_no'))['client_no__max'] or 0
                    client = Client.objects.create(client_no=max_no + 1,
                                                   clientname=name, phone=phone)
            if paid < total_final and client is None:
                raise ValueError("Enter the customer's name and phone to record a balance.")

            status = 'Paid' if paid >= total_final else ('Partial' if paid > 0 else 'Unpaid')
            memo = f"In-Store | {payment}"
            if paid < total_final:
                memo += f" | Balance {total_final - paid:.2f}"

            try:
                emp = Employee.objects.get(employeeid=cashier_id)
            except Employee.DoesNotExist:
                raise ValueError("Selected Cashier does not exist in the employee database.")

            with connection.cursor() as cur:
                cur.execute("""
                    INSERT INTO invoices
                        (invoice_date, client_no, employeeid, invoice_status,
                         invoicememo, total_amount, amount_paid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING invoiceno;
                """, [timezone.now(), client.client_no if client else None,
                      emp.employeeid, status, memo, total_final, paid])
                invoice_no = cur.fetchone()[0]

            for product, qty, unit in priced:
                with connection.cursor() as cur:
                    cur.execute("""
                        INSERT INTO invoice_details (invoiceno, product_no, qty, price)
                        VALUES (%s, %s, %s, %s)
                    """, [invoice_no, product.product_no, qty, unit])
                product.qty_on_hand -= qty
                product.save()

            return invoice_no

    try:
        invoice_no = await in_thread(_do_sale)
    except Product.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Product not found.'}, status=400)
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)

    return JsonResponse({'ok': True, 'receipt_url': reverse('pos_receipt', args=[invoice_no])})


async def pos_receipt_view(request, invoiceno):
    invoice = await aget_object_or_404(
        Invoice.objects.select_related('client'), invoiceno=invoiceno)

    items = [
        {'productname': r['product_no__productname'], 'qty': r['qty'],
         'price': float(r['price']), 'line_total': float(r['qty'] * r['price'])}
        async for r in InvoiceDetail.objects.filter(invoiceno_id=invoiceno)
        .order_by('product_no__productname')
        .values('product_no__productname', 'qty', 'price')
    ]

    total = float(invoice.total_amount or 0)
    paid = float(invoice.amount_paid or 0)
    return render(request, 'backoffice/sales/pos_receipt.html', {
        'order': invoice, 'items': items, 'subtotal': total, 'discount': 0.00,
        'total_amount': total, 'paid': paid, 'balance': total - paid,
    })


# ═════════════════════════════════════════════════════════════
# Customers and report
# ═════════════════════════════════════════════════════════════
@admin_required
async def customers_view(request):
    q = request.GET.get('q', '').strip()
    client_id = request.GET.get('id', '').strip()
    date_from = _parse_date(request.GET.get('date_from', '').strip())
    date_to = _parse_date(request.GET.get('date_to', '').strip())
    if date_from and not date_to:
        date_to = date_from

    inv_q = Q()
    if date_from:
        inv_q &= Q(invoice__invoice_date__date__gte=date_from)
    if date_to:
        inv_q &= Q(invoice__invoice_date__date__lte=date_to)
    inv_filter = inv_q or None

    qs = Client.objects.annotate(
        total_spent=Coalesce(Sum('invoice__total_amount', filter=inv_filter), 0, output_field=MONEY),
        orders_count=Count('invoice', filter=inv_filter),
        last_purchase=Max('invoice__invoice_date', filter=inv_filter),
    ).order_by('clientname')

    if date_from or date_to:
        qs = qs.filter(orders_count__gt=0)
    if q:
        qs = qs.filter(clientname__icontains=q)
    if client_id.isdigit():
        qs = qs.filter(client_no=int(client_id))

    clients = [c async for c in qs]

    return render(request, 'backoffice/customers/customers.html', {
        'clients': clients,
        'total_clients': len(clients),
        'total_spent_all': sum(c.total_spent for c in clients),
        'q': q, 'client_id': client_id,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to and date_to != date_from else '',
    })


async def add_customer_view(request):
    client_types = [t async for t in ClientType.objects.all()]
    errors, form_data = [], {}

    if request.method == 'POST':
        form_data = {k: (request.POST.get(k) or '').strip() for k in
                     ('clientname', 'address', 'city', 'phone', 'client_type', 'discount')}

        if not form_data['clientname']:
            errors.append("Customer name is required.")

        discount = None
        if form_data['discount']:
            try:
                discount = Decimal(form_data['discount'])
                if not (0 <= discount <= 100):
                    raise ValueError
            except Exception:
                errors.append("Discount must be a number between 0 and 100.")

        phone = form_data['phone']
        if not errors and phone and await Client.objects.filter(phone=phone).aexists():
            errors.append("A customer with this phone number already exists.")

        if not errors:
            ctype = None
            if form_data['client_type'].isdigit():
                ctype = await ClientType.objects.filter(pk=int(form_data['client_type'])).afirst()
            max_no = (await Client.objects.aaggregate(m=Max('client_no')))['m'] or 0

            await Client.objects.acreate(
                client_no=max_no + 1,
                clientname=form_data['clientname'],
                address=form_data['address'] or None,
                city=form_data['city'] or None,
                phone=phone or None,
                client_type=ctype,
                discount=discount,
            )
            messages.success(request, "Customer added successfully.")
            return redirect('customers')

    return render(request, 'backoffice/customers/add_customers.html',
                  {'errors': errors, 'form_data': form_data, 'client_types': client_types})


@admin_required
async def report_view(request):
    invoiceno = request.GET.get('invoiceno', '').strip()
    client_no = request.GET.get('client_no', '').strip()
    clientname = request.GET.get('clientname', '').strip()

    qs = Invoice.objects.select_related('client', 'employee').order_by('-invoice_date')
    if invoiceno.isdigit():
        qs = qs.filter(invoiceno=int(invoiceno))
    if client_no.isdigit():
        qs = qs.filter(client_id=int(client_no))
    if clientname:
        qs = qs.filter(client__clientname__icontains=clientname)
    invoices = [i async for i in qs]

    return render(request, 'backoffice/dashboard/report.html', {
        'invoices': invoices, 'invoiceno': invoiceno, 'client_no': client_no,
        'clientname': clientname, 'total_rows': len(invoices),
    })


# ═════════════════════════════════════════════════════════════
# Employees and jobs
# ═════════════════════════════════════════════════════════════
@admin_required
async def employees_view(request):
    q = request.GET.get('q', '').strip()
    qs = Employee.objects.select_related('job').order_by('employeename')
    if q:
        qs = qs.filter(employeename__icontains=q)
    employees = [e async for e in qs]
    return render(request, 'backoffice/hr/employees.html',
                  {'employees': employees, 'total_employees': len(employees), 'q': q})


async def employee_form_view(request, employeeid=None):
    employee = None
    if employeeid is not None:
        employee = await aget_object_or_404(Employee, employeeid=employeeid)

    jobs = [j async for j in Job.objects.order_by('job_title')]
    errors = []

    if request.method == 'POST':
        form = {k: (request.POST.get(k) or '').strip() for k in
                ('employeename', 'gender', 'birthdate', 'job', 'address')}

        if not form['employeename']:
            errors.append("Employee name is required.")
        birthdate = _parse_date(form['birthdate']) if form['birthdate'] else None
        if form['birthdate'] and birthdate is None:
            errors.append("Birth date is not valid.")

        if not errors:
            job = None
            if form['job'].isdigit():
                job = await Job.objects.filter(pk=int(form['job'])).afirst()

            new = employee is None
            if new:
                max_no = (await Employee.objects.aaggregate(m=Max('employeeid')))['m'] or 0
                employee = Employee(employeeid=max_no + 1)

            employee.employeename = form['employeename']
            employee.gender = form['gender'] or None
            employee.birthdate = birthdate
            employee.job = job
            employee.address = form['address'] or None
            await employee.asave(force_insert=new)

            messages.success(request, "Employee saved.")
            return redirect('employees')
    else:
        form = {}
        if employee:
            form = {
                'employeename': employee.employeename,
                'gender': employee.gender or '',
                'birthdate': employee.birthdate.isoformat() if employee.birthdate else '',
                'job': str(employee.job_id) if employee.job_id else '',
                'address': employee.address or '',
            }

    return render(request, 'backoffice/hr/employee_form.html',
                  {'form': form, 'errors': errors, 'jobs': jobs, 'employee': employee})


async def delete_employee_view(request, employeeid):
    if request.method == 'POST':
        employee = await aget_object_or_404(Employee, employeeid=employeeid)
        await employee.adelete()
        messages.success(request, "Employee deleted.")
    return redirect('employees')


async def jobs_view(request):
    jobs = [j async for j in Job.objects.order_by('job_title')]
    editing = None
    edit_id = request.GET.get('edit', '')
    if edit_id.isdigit():
        editing = next((j for j in jobs if j.job_id == int(edit_id)), None)
    return render(request, 'backoffice/hr/jobs.html', {'jobs': jobs, 'editing': editing})


async def job_save_view(request, job_id=None):
    if request.method != 'POST':
        return redirect('jobs')

    title = (request.POST.get('job_title') or '').strip()
    try:
        min_salary = Decimal(request.POST['min_salary']) if request.POST.get('min_salary') else None
        max_salary = Decimal(request.POST['max_salary']) if request.POST.get('max_salary') else None
    except Exception:
        messages.error(request, "Salary must be a number.")
        return redirect('jobs')

    if not title:
        messages.error(request, "Job title is required.")
        return redirect('jobs')
    if min_salary and max_salary and min_salary > max_salary:
        messages.error(request, "Minimum salary cannot be higher than maximum.")
        return redirect('jobs')

    if job_id is not None:
        job = await Job.objects.filter(pk=job_id).afirst()
        if job is None:
            messages.error(request, "Job not found.")
            return redirect('jobs')
        new = False
    else:
        if await Job.objects.filter(job_title__iexact=title).aexists():
            messages.error(request, "That job already exists.")
            return redirect('jobs')
        max_no = (await Job.objects.aaggregate(m=Max('job_id')))['m'] or 0
        job = Job(job_id=max_no + 1)
        new = True

    job.job_title, job.min_salary, job.max_salary = title, min_salary, max_salary
    await job.asave(force_insert=new)
    messages.success(request, "Job saved.")
    return redirect('jobs')


async def delete_job_view(request, job_id):
    if request.method == 'POST':
        try:
            job = await aget_object_or_404(Job, job_id=job_id)
            await job.adelete()
            messages.success(request, "Job deleted.")
        except Exception:
            messages.error(request, "This job cannot be deleted.")
    return redirect('jobs')


# ═════════════════════════════════════════════════════════════
# Customer sign in / register
# ═════════════════════════════════════════════════════════════
async def login_view(request):
    user = await request.auser()
    if user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        user = await aauthenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password'),
        )
        if user is not None:
            await alogin(request, user)
            return redirect(_safe_next(request, 'home'))
        messages.error(request, "Invalid username or password.")

    return render(request, 'shop/login.html', {'next': request.GET.get('next', '')})


async def register_view(request):
    user = await request.auser()
    if user.is_authenticated:
        return redirect('home')

    errors, form = [], {}
    if request.method == 'POST':
        form = {k: (request.POST.get(k) or '').strip() for k in
                ('username', 'full_name', 'phone', 'email')}
        password = request.POST.get('password') or ''
        confirm = request.POST.get('confirm') or ''

        if len(form['username']) < 3:
            errors.append("Username must be at least 3 characters.")
        if not form['full_name']:
            errors.append("Full name is required.")
        if not form['phone']:
            errors.append("Phone number is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if form['username'] and await User.objects.filter(
                username__iexact=form['username']).aexists():
            errors.append("That username is already taken.")

        if not errors:
            new_user = await User.objects.acreate_user(
                username=form['username'], email=form['email'],
                password=password, first_name=form['full_name'])

            if not await Client.objects.filter(phone=form['phone']).aexists():
                max_no = (await Client.objects.aaggregate(m=Max('client_no')))['m'] or 0
                await Client.objects.acreate(client_no=max_no + 1,
                                             clientname=form['full_name'], phone=form['phone'])

            await alogin(request, new_user)
            messages.success(request, "Account created. Welcome!")
            return redirect(_safe_next(request, 'home'))

    return render(request, 'shop/register.html',
                  {'errors': errors, 'form': form, 'next': request.GET.get('next', '')})


async def logout_view(request):
    if request.method == 'POST':
        await alogout(request)
    return redirect('home')


# ═════════════════════════════════════════════════════════════
# Admin / staff sign in
# ═════════════════════════════════════════════════════════════
async def _staff_role(user):
    if user.is_superuser:
        return 'admin'
    if await user.groups.filter(name='Stock Controllers').aexists():
        return 'stock'
    return 'cashier'


def _role_redirect(role):
    return redirect({'admin': 'dashboard', 'stock': 'products'}.get(role, 'pos'))


async def login_admin_view(request):
    user = await request.auser()

    if user.is_authenticated and not user.is_staff:
        return redirect('home')
    if user.is_authenticated and user.is_staff:
        return _role_redirect(await _staff_role(user))

    if request.method == 'POST':
        ident = (request.POST.get('username') or '').strip()
        password = request.POST.get('password')

        username = ident
        if '@' in ident:
            by_email = await User.objects.filter(email=ident).afirst()
            username = by_email.username if by_email else ''

        user = await aauthenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            await alogin(request, user)
            return _role_redirect(await _staff_role(user))

        messages.error(request, "Access denied. Invalid credentials.")

    return render(request, 'backoffice/auth/login_admin.html')


async def logout_admin_view(request):
    await alogout(request)
    return redirect('login_admin')

async def outstanding_balances_view(request):
    def _get_balances():
        from .models import Client
        from django.db.models import Sum
        
        # Get all clients and calculate their total invoiced vs total paid
        clients = Client.objects.annotate(
            total_invoiced=Sum('invoice__total_amount'),
            total_paid=Sum('invoice__amount_paid')
        ).filter(total_invoiced__gt=0)
        
        outstanding_list = []
        total_outstanding_all = 0

        for c in clients:
            invoiced = c.total_invoiced or 0
            paid = c.total_paid or 0
            balance = invoiced - paid
            
            if balance > 0:
                outstanding_list.append({
                    'client_no': c.client_no,
                    'clientname': c.clientname,
                    'phone': c.phone or 'N/A',
                    'invoiced': invoiced,
                    'paid': paid,
                    'balance': balance,
                })
                total_outstanding_all += balance

        outstanding_list.sort(key=lambda x: x['balance'], reverse=True)
        return outstanding_list, total_outstanding_all

    outstanding_list, total_outstanding_all = await sync_to_async(_get_balances, thread_sensitive=True)()

    return render(request, 'backoffice/customers/outstanding_balances.html', {
        'clients': outstanding_list,
        'total_outstanding': total_outstanding_all,
        'user_is_authenticated': request.user.is_authenticated,
        'user_username': request.user.username if request.user.is_authenticated else "",
        'user_is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
    })
    

async def customer_statement_view(request, client_no):
    def _get_data():
        from .models import Client, Invoice
        from django.db.models import Sum
        
        client = Client.objects.filter(client_no=client_no).first()
        if not client:
            return None, [], 0, 0
            
        # Get all their invoices
        invoices = list(Invoice.objects.filter(client_id=client_no).order_by('-invoice_date'))
        
        total_invoiced = sum(inv.total_amount for inv in invoices)
        total_paid = sum(inv.amount_paid for inv in invoices)
        balance = total_invoiced - total_paid
        
        return client, invoices, total_invoiced, balance

    client, invoices, total_invoiced, balance = await sync_to_async(_get_data, thread_sensitive=True)()

    if not client:
        return redirect('outstanding_balances')

    return render(request, 'backoffice/customers/customer_statement.html', {
        'client': client,
        'invoices': invoices,
        'total_invoiced': total_invoiced,
        'balance': balance,
    })