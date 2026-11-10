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

# Deploy on Vercel

Vercel functions have a read-only, temporary disk, so this version stores data outside the server:
**Postgres** (orders, products, users, chat, payment screenshots) and **Cloudinary** (product images & videos).
Running locally still works exactly as before (SQLite + local files) when no `DATABASE_URL` is set.

1. Push the project to GitHub and import it in Vercel (Framework: Flask is detected from `app.py`).
2. **Database:** Vercel dashboard → *Storage* → create a **Neon Postgres** database and connect it to the project. This adds `DATABASE_URL` / `POSTGRES_URL` automatically.
3. **Cloudinary (free):** create an account → *Settings → Upload → Upload presets → Add preset* → set **Signing mode: Unsigned**. Note your *Cloud name* and the preset name.
4. In Vercel → *Settings → Environment Variables* add:
   | Name | Value |
   |---|---|
   | `SECRET_KEY` | a long random string |
   | `ADMIN_EMAIL` | your admin login email |
   | `ADMIN_PASSWORD` | a strong password (used once, when the admin account is first created) |
   | `CLOUDINARY_CLOUD_NAME` | your cloud name |
   | `CLOUDINARY_UPLOAD_PRESET` | your unsigned preset name |
5. Deploy. Open `/login` with the admin email/password, then set up **Payment settings** and add products.

Notes
- Product images/videos upload straight from the browser to Cloudinary (no size problems with Vercel's 4.5 MB request limit). Images up to 8 MB, videos up to 100 MB.
- Payment screenshots in the order chat are stored in the database and are shrunk in the browser before upload (Vercel allows about 4.5 MB per request).
- Removing a file in the admin panel removes it from the product; the original stays in your Cloudinary library.
- The loading screen was removed, so pages no longer show it on every click.

## Speed on Vercel
- Put the **Vercel Function Region and the Neon database in the same region** (Vercel: *Settings → Functions → Function Region*; Neon region is shown in *Storage → your database*). Different regions make every database query slow.
- The app re-uses database connections, writes at most one visit per visitor per day, and caches settings for 30 seconds.

## Mobile & speed (latest)
- Default theme is now **light** (dark is still one tap away). Phones and weak devices automatically get a lighter look (`html.lite`): fewer shapes, no heavy blur/shadow effects. If the 3D background runs slowly it switches itself off.
- CSS and JS are combined into `public/static/site.css` and `site.js`. **After editing `style.css`, `upgrade.css`, `stark.css`, `app.js` or `stark.js`, run `python build_assets.py`** and commit the new `site.*` files.
- Static files are cached for a year (`vercel.json`); URLs carry a version so updates still reach visitors.
- Cloudinary pictures are requested at the size needed (small for cards, larger on the product page); video thumbnails use a still image.

## Colour & size options, product description
- Admin → Products (add / edit): fill **Colours** and/or **Sizes** (comma separated, or tap the quick buttons). Leave empty for products without options.
- The customer must pick a colour/size on the product page before *Add to bag* or *Buy now*; cards of such products show **Choose options**. The choice is kept in the bag, checkout, order chat, order history and the admin order page. Each colour/size combination is its own bag line.
- Stock is still counted per product (not per colour/size).
- The product description now has its own **Product Description** section below the photos and details (line breaks are kept).
- Existing databases are updated automatically on the next start.
