const express = require('express');
const swaggerUi = require('swagger-ui-express');

const app = express();
app.use(express.json());

const products = [
  { id: 1, name: 'Mouse', price: 25 },
  { id: 2, name: 'Keyboard', price: 80 },
  { id: 3, name: 'Mug', price: 12 },
];
let cart = []; // ponytail: one global cart, add per-user carts when you have users
const orders = [];

const total = (items) => items.reduce((s, i) => s + i.price * i.quantity, 0);
const order = (items, name, address) => {
  const o = { id: orders.length + 1, items, total: total(items), name, address };
  orders.push(o);
  return o;
};

app.get('/products', (req, res) => res.json(products));

app.get('/cart', (req, res) => res.json({ items: cart, total: total(cart) }));

app.post('/cart', (req, res) => {
  const { productId, quantity = 1 } = req.body;
  const p = products.find((x) => x.id === productId);
  if (!p) return res.status(404).json({ error: 'Product not found' });
  if (!Number.isInteger(quantity) || quantity < 1) return res.status(400).json({ error: 'quantity must be >= 1' });
  const item = cart.find((i) => i.productId === p.id);
  if (item) item.quantity += quantity;
  else cart.push({ productId: p.id, name: p.name, price: p.price, quantity });
  res.status(201).json({ items: cart, total: total(cart) });
});

app.delete('/cart/:productId', (req, res) => {
  cart = cart.filter((i) => i.productId !== Number(req.params.productId));
  res.json({ items: cart, total: total(cart) });
});

app.post('/checkout', (req, res) => {
  const { name, address } = req.body;
  if (!name || !address) return res.status(400).json({ error: 'name and address required' });
  if (!cart.length) return res.status(400).json({ error: 'Cart is empty' });
  const o = order(cart, name, address);
  cart = [];
  res.status(201).json(o);
});

app.post('/buy', (req, res) => {
  const { productId, quantity = 1, name, address } = req.body;
  const p = products.find((x) => x.id === productId);
  if (!p) return res.status(404).json({ error: 'Product not found' });
  if (!Number.isInteger(quantity) || quantity < 1) return res.status(400).json({ error: 'quantity must be >= 1' });
  if (!name || !address) return res.status(400).json({ error: 'name and address required' });
  res.status(201).json(order([{ productId: p.id, name: p.name, price: p.price, quantity }], name, address));
});

app.get('/orders', (req, res) => res.json(orders));

app.use('/docs', swaggerUi.serve, swaggerUi.setup(require('./swagger.json')));

app.listen(3000, () => console.log('http://localhost:3000/docs'));
