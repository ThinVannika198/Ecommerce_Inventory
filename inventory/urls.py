from django.urls import path

from .import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/month/', views.month_customers_view, name='dashboard_month'),
    path('products/', views.products_view, name='products'),
    path('categories/', views.categories_view, name='categories'),
    
    
    path('orders/', views.orders_view, name='orders'),
    path('product/<int:product_no>/', views.product_detail_view, name='product_detail'),
    
    path('cart/add/<int:product_no>/', views.add_to_cart_view, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart_page'),
    path('cart/update/<int:product_no>/', views.update_cart_view, name='update_cart'),
    path('cart/remove/<int:product_no>/', views.remove_from_cart_view, name='remove_from_cart'),
    path('collection/', views.collection_view, name='collection'),
    path('about/', views.about_view, name='about'),
    
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/success/', views.checkout_success_view, name='checkout_success'),
    
    path('categories/', views.categories_view, name='categories_page'),
    path('categories/add/', views.add_category_view, name='add_category'),
    path('categories/delete/<int:pk>/', views.delete_category_view, name='delete_category'),
    path('categories/edit/<int:category_id>/', views.edit_category_view, name='edit_category'),
    
    path('products/', views.products_view, name='products'),           # admin list
    path('product/add/', views.add_product_view, name='add_product'),
    path('products/edit/<int:product_no>/', views.edit_product_view, name='edit_product'),
    path('products/delete/<int:product_no>/', views.delete_product_view, name='delete_product'),
    
    path('suppliers/', views.suppliers_view, name='suppliers'),
    path('suppliers/add/', views.add_supplier_view, name='add_supplier'),
    path('suppliers/edit/<int:supplier_no>/', views.edit_supplier_view, name='edit_supplier'),
    path('suppliers/delete/<int:supplier_no>/', views.delete_supplier_view, name='delete_supplier'),
    
    path('stock/', views.stock_management_view, name='stock'),
    path('stock/adjust/', views.stock_adjustment_view, name='stock_adjustment'),
    
    path('orders/', views.orders_view, name='orders_list'),
    path('orders/<int:invoiceno>/', views.order_detail_view, name='order_detail'),
    path('pos/', views.pos_view, name='pos'),
    path('pos/checkout/', views.pos_checkout_view, name='pos_checkout'),
    path('pos/receipt/<int:invoiceno>/', views.pos_receipt_view, name='pos_receipt'),
    path('orders/<int:invoiceno>/pay/', views.add_payment_view, name='add_payment'),
        
    path('customers/', views.customers_view, name='customers'),
    path('customers/add/', views.add_customer_view, name='add_customer'),
    
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    
    path('employees/', views.employees_view, name='employees'),
    path('employees/add/', views.employee_form_view, name='add_employee'),
    path('employees/edit/<int:employeeid>/', views.employee_form_view, name='edit_employee'),
    path('employees/delete/<int:employeeid>/', views.delete_employee_view, name='delete_employee'),
    
    path('jobs/', views.jobs_view, name='jobs'),
    path('jobs/save/', views.job_save_view, name='save_job'),
    path('jobs/save/<int:job_id>/', views.job_save_view, name='edit_job'),
    path('jobs/delete/<int:job_id>/', views.delete_job_view, name='delete_job'),
    path('report/', views.report_view, name='report'),
    path('report/outstanding/', views.outstanding_balances_view, name='outstanding_balances'),
    path('report/outstanding/statement/<int:client_no>/', views.customer_statement_view, name='customer_statement'),
    
    path('login_admin/', views.login_admin_view, name='login_admin'),
    path('logout_admin/', views.logout_admin_view, name='logout_admin'),
    
    path('purchase/add/', views.add_purchase_view, name='add_purchase'),
]