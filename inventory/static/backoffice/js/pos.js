(function () {
    const app = document.getElementById('pos-app');
    const checkoutUrl = app.dataset.checkoutUrl;
    const products = JSON.parse(document.getElementById('products-data').textContent);
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const cart = {};   // product_no -> {product, qty, disc}

    const grid = document.getElementById('product-grid');
    const cartBox = document.getElementById('cart-items');
    const totalEl = document.getElementById('total');
    const changeEl = document.getElementById('change');
    const owedEl = document.getElementById('owed');
    const receivedEl = document.getElementById('received');
    const paymentEl = document.getElementById('payment');
    const debtEl = document.getElementById('allow-debt');
    const errorEl = document.getElementById('error');
    const chargeBtn = document.getElementById('charge');
    
    // NEW: Get the cashier dropdown element
    const cashierSelect = document.getElementById('cashier-select');

    const money = n => '$' + n.toFixed(2);

    function showError(msg) { errorEl.textContent = msg; }

    // price after discount, rounded to cents (same rule as the server)
    function unitPrice(l) {
        return Math.round(l.product.price * (1 - l.disc / 100) * 100) / 100;
    }
    function lineTotal(l) {
        return Math.round(unitPrice(l) * l.qty * 100) / 100;
    }
    function cartTotal() {
        return Object.values(cart).reduce((s, l) => s + lineTotal(l), 0);
    }

    function renderProducts(filter = '') {
        grid.innerHTML = '';
        products
            .filter(p => p.name.toLowerCase().includes(filter.toLowerCase()))
            .forEach(p => {
                const card = document.createElement('button');
                card.type = 'button';
                card.className = 'product-card' + (p.qty <= 0 ? ' out' : '');
                card.disabled = p.qty <= 0;
                card.innerHTML = `
                    <div class="product-img">${p.photo ? `<img src="${p.photo}" alt="">` : '📦'}</div>
                    <div class="product-name"></div>
                    <div class="product-price">${money(p.price)}</div>
                    <div class="product-stock">${p.qty > 0 ? p.qty + ' in stock' : 'Out of stock'}</div>`;
                card.querySelector('.product-name').textContent = p.name;
                card.addEventListener('click', () => addToCart(p));
                grid.appendChild(card);
            });
    }

    function addToCart(p) {
        const line = cart[p.product_no] || { product: p, qty: 0, disc: 0 };
        if (line.qty >= p.qty) {
            showError('Only ' + p.qty + ' of ' + p.name + ' in stock.');
            return;
        }
        line.qty++;
        cart[p.product_no] = line;
        showError('');
        renderCart();
    }

    function changeQty(no, delta) {
        const line = cart[no];
        if (!line) return;
        line.qty += delta;
        if (line.qty <= 0) delete cart[no];
        else if (line.qty > line.product.qty) line.qty = line.product.qty;
        renderCart();
    }

    function renderCart() {
        cartBox.innerHTML = '';
        const lines = Object.values(cart);
        if (!lines.length) cartBox.innerHTML = '<p class="cart-empty">Click a product to add it.</p>';

        lines.forEach(l => {
            const row = document.createElement('div');
            row.className = 'cart-row';
            row.innerHTML = `
                <div class="cart-name"></div>
                <select class="cart-disc" title="Discount %"></select>
                <div class="cart-qty">
                    <button type="button" data-d="-1">−</button>
                    <span>${l.qty}</span>
                    <button type="button" data-d="1">+</button>
                </div>
                <div class="cart-line"></div>`;

            row.querySelector('.cart-name').textContent = l.product.name;

            // discount dropdown 0% to 100%
            const sel = row.querySelector('.cart-disc');
            for (let i = 0; i <= 100; i++) {
                const o = document.createElement('option');
                o.value = i;
                o.textContent = i + '%';
                if (i === l.disc) o.selected = true;
                sel.appendChild(o);
            }
            sel.addEventListener('change', () => {
                l.disc = parseInt(sel.value, 10);
                renderCart();
            });

            // line price: show the old price crossed out when discounted
            const lineEl = row.querySelector('.cart-line');
            const full = l.product.price * l.qty;
            lineEl.innerHTML = l.disc > 0
                ? `<s class="old-price">${money(full)}</s><br>${money(lineTotal(l))}`
                : money(full);

            row.querySelectorAll('.cart-qty button').forEach(b =>
                b.addEventListener('click', () =>
                    changeQty(l.product.product_no, parseInt(b.dataset.d))));
            cartBox.appendChild(row);
        });

        totalEl.textContent = money(cartTotal());
        updateChange();
    }

    function updateChange() {
        const received = parseFloat(receivedEl.value) || 0;
        const total = cartTotal();
        changeEl.textContent = money(Math.max(0, received - total));
        owedEl.textContent = money(Math.max(0, total - received));
        debtEl.checked = received > 0 && received < total;
    }

    // ---- events ----
    paymentEl.addEventListener('change', () => {
        document.getElementById('cash-box').style.display =
            paymentEl.value === 'Cash' ? 'block' : 'none';
    });

    receivedEl.addEventListener('input', updateChange);

    document.getElementById('search').addEventListener('input', e =>
        renderProducts(e.target.value));

    document.getElementById('clear').addEventListener('click', () => {
        Object.keys(cart).forEach(k => delete cart[k]);
        receivedEl.value = '';
        showError('');
        renderCart();
    });

    chargeBtn.addEventListener('click', async () => {
        const lines = Object.values(cart);
        if (!lines.length) { showError('The cart is empty.'); return; }

        // NEW: Check if the cashier selected their name
        const cashierId = cashierSelect ? cashierSelect.value : null;
        if (!cashierId) {
            showError('Please select your name from the "Select Cashier" dropdown.');
            return;
        }

        chargeBtn.disabled = true;
        try {
            const res = await fetch(checkoutUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                body: JSON.stringify({
                    items: lines.map(l => ({
                        product_no: l.product.product_no,
                        qty: l.qty,
                        discount: l.disc,
                    })),
                    payment_method: paymentEl.value,
                    received: receivedEl.value,
                    name: document.getElementById('cust-name').value,
                    phone: document.getElementById('cust-phone').value,
                    allow_debt: debtEl.checked,
                    cashier_id: cashierId, // NEW: Send cashier ID to backend
                }),
            });
            const data = await res.json();
            if (data.ok) {
                // empty the cart first so the "leave page?" warning doesn't appear
                Object.keys(cart).forEach(k => delete cart[k]);
                window.location.href = data.receipt_url;
            } else {
                showError(data.error);
                chargeBtn.disabled = false;
            }
        } catch (e) {
            showError('Network error. Please try again.');
            chargeBtn.disabled = false;
        }
    });

    // warn before leaving the page with items in the cart
    window.addEventListener('beforeunload', e => {
        if (Object.keys(cart).length) { e.preventDefault(); e.returnValue = ''; }
    });

    renderProducts();
    renderCart();
})();