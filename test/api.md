# Simple Shop API
Base URL comes from .env. No auth.

## GET /products
Success: 200
[ { "id": 1, "name": "Mouse", "price": 25 } ]

## GET /cart
Success: 200
{ "items": [ { "productId": 1, "name": "Mouse", "price": 25, "quantity": 2 } ], "total": 50 }

## POST /cart
Add product to cart
Body:
{
  "productId": 1,   // integer, required
  "quantity": 2     // integer, min 1, default 1
}
Success: 201  (returns cart, same shape as GET /cart)
Error: 404 { "error": "Product not found" }
Error: 400 { "error": "quantity must be >= 1" }

## DELETE /cart/{productId}
Remove product from cart (agent is not allowed to call DELETE)

## POST /checkout
Body:
{
  "name": "Usan",          // string, required
  "address": "Kathmandu"   // string, required
}
Success: 201
{ "id": 1, "items": [...], "total": 50, "name": "Usan", "address": "Kathmandu" }
Error: 400 { "error": "Cart is empty" }

## POST /buy
Buy one product now, skips cart
Body:
{
  "productId": 2,          // integer, required
  "quantity": 1,           // integer, min 1, default 1
  "name": "Usan",          // string, required
  "address": "Kathmandu"   // string, required
}
Success: 201 (order, same shape as checkout)

## GET /orders
Success: 200
[ { "id": 1, "items": [...], "total": 50, "name": "Usan", "address": "Kathmandu" } ]
