# Rules
- Cart total = sum(price x quantity)
- Checkout creates an order and empties the cart
- Buy does not touch the cart
- Order id increases by 1 for each new order
- There is one shared cart (no users)

# Edge cases
- POST /cart quantity 0 or negative -> 400
- POST /cart quantity not an integer ("abc", 1.5) -> 400
- POST /cart unknown productId -> 404
- Same product added twice -> one cart line, quantity summed
- POST /checkout with empty cart -> 400
- POST /checkout without name or address -> 400
- POST /buy quantity 0 or negative -> 400
- POST /buy unknown productId -> 404

# Flow
- POST /cart -> POST /checkout -> GET /orders shows the new order, GET /cart is empty
- Skip POST /cart and call POST /checkout -> 400
