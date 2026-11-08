# Stark Store

A responsive Flask + SQLite starter e-commerce website with a customer storefront and a protected Super Admin dashboard.

## Run locally (Windows)

1. Install Python 3.11+.
2. Extract this ZIP.
3. Open Command Prompt in the `stark_store` folder.
4. Run:

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set ADMIN_EMAIL=your-email@example.com
set ADMIN_PASSWORD=Choose-A-Strong-Password
set SECRET_KEY=replace-with-a-long-random-secret
py app.py
```

5. Open http://127.0.0.1:5000
6. Sign in using the admin email and password you set above.

If you omit environment variables on first run, the local starter admin is:
- Email: `admin@starkstore.local`
- Password: `ChangeMe123!`

Change these before using the site with real customers. The admin account is created only when the database is first initialized. To reset a local test install, stop the app and delete `stark_store.db`, then start it again with your chosen environment variables.

## Included

- Public product catalogue, search and category filter
- Guest shopping and optional customer registration/login
- Cart and Cash on Delivery checkout
- Stock reduction when an order is placed
- Customer product reviews, held for admin approval
- Admin product create/edit/hide/delete, image upload, price, discount and stock
- Order list and status management
- Dashboard totals for sales, orders, products, customers, visits and pending reviews
- Daily page-view counts and top-selling products

## Important before going live

This is a functional starter, not a fully production-hardened hosted shop. It currently supports Cash on Delivery only; card, bank, Easypaisa/JazzCash payments need a merchant account and a verified payment gateway integration. Visit counts are page views, not unique visitors. Add CSRF protection, HTTPS, secure environment secrets, backups, rate limiting, transactional email, privacy/terms pages and production hosting before accepting public traffic. Use a production WSGI server (for example Waitress on Windows or Gunicorn on Linux), not Flask's development server. Set `debug` off.


## Purple Edition — payment configuration

Checkout includes Cash on Delivery, bank transfer, Easypaisa, JazzCash, and a debit/credit-card gateway placeholder. COD works immediately. Bank and wallet payments are manual: the customer enters a transaction reference and Super Admin verifies it in Orders. Card processing is not active until a real merchant gateway is connected; this site never collects card numbers itself.

Set your real payment destinations before accepting manual transfers. Windows CMD (for the current terminal):
```bat
set STARK_BANK_DETAILS=Bank name | Account title | IBAN
set STARK_EASYPAISA_NUMBER=03XXXXXXXXX
set STARK_JAZZCASH_NUMBER=03XXXXXXXXX
py app.py
```
Do not mark an order Paid until funds are confirmed. For live card payments, connect a supported merchant gateway and store its API keys server-side.

## Payments, order history & order chat (v3)
- Admin → **Payment settings**: turn Cash on Delivery / Bank / Easypaisa / JazzCash / Card on or off and set account details (no env vars needed any more; old env vars are used only as starting values).
- Every order starts as **Pending** and opens an order chat. The assistant asks the customer to confirm order + address. COD is confirmed automatically; for online methods the assistant sends the account details and asks for a payment screenshot, then an agent confirms.
- Customers: **Orders** link in the menu (history + chat). Admin: **Orders** → filter by Pending / Confirmed / On its way / Delivered, open an order to chat, view the screenshot and change status.
- Payment screenshots are stored in `private_uploads/` and only served to the order's owner and admins.

## Product images & videos (v4)
- Admin → Products: select several images and videos at once (add more in several rounds, remove with ×). Images up to 8 MB, videos (MP4/WEBM/MOV) up to 100 MB each, max 12 files per upload.
- Edit product: see all files, make any image the cover, remove files, add more.
- Product page: gallery with thumbnails, arrows, swipe/keyboard and an inline video player. Older single product images are migrated automatically.
