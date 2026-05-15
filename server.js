const express = require('express');
const cors = require('cors');
const { Telegraf } = require('telegraf');
const { Pool } = require('pg');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

// Автосоздание таблиц
(async () => {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS clients (
      id SERIAL PRIMARY KEY,
      phone VARCHAR(20) UNIQUE NOT NULL,
      full_name VARCHAR(255),
      created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS deals (
      id SERIAL PRIMARY KEY,
      client_phone VARCHAR(20),
      product_name VARCHAR(255),
      source VARCHAR(50) DEFAULT 'call',
      status VARCHAR(30) DEFAULT 'new',
      comment TEXT,
      created_at TIMESTAMP DEFAULT NOW()
    );
  `);
})();

// API – получить заявки
app.get('/api/deals', async (req, res) => {
  const { rows } = await pool.query('SELECT * FROM deals ORDER BY id DESC LIMIT 100');
  res.json(rows);
});

// API – создать заявку
app.post('/api/deals', async (req, res) => {
  const { client_phone, product_name, source, comment } = req.body;
  const { rows } = await pool.query(
    `INSERT INTO deals (client_phone, product_name, source, comment) VALUES ($1,$2,$3,$4) RETURNING *`,
    [client_phone, product_name, source || 'call', comment]
  );
  res.json(rows[0]);
});

// API – сменить статус
app.patch('/api/deals/:id', async (req, res) => {
  const { status } = req.body;
  await pool.query('UPDATE deals SET status=$1 WHERE id=$2', [status, req.params.id]);
  res.json({ ok: true });
});

// Telegram Bot
const bot = new Telegraf(process.env.BOT_TOKEN);
bot.command('start', ctx => ctx.reply('Привет! Я CRM-бот.\n/new_deal — создать заявку'));
bot.command('new_deal', ctx => {
  ctx.session = { step: 'phone' };
  ctx.reply('Введите номер телефона клиента:');
});
bot.on('text', async ctx => {
  if (!ctx.session) return;
  if (ctx.session.step === 'phone') {
    ctx.session.phone = ctx.message.text;
    ctx.session.step = 'product';
    ctx.reply('Введите название товара (или "пропустить"):');
  } else if (ctx.session.step === 'product') {
    const product = ctx.message.text === 'пропустить' ? '' : ctx.message.text;
    await pool.query(
      'INSERT INTO deals (client_phone, product_name, source, comment) VALUES ($1,$2,$3,$4)',
      [ctx.session.phone, product, 'telegram', 'создано ботом']
    );
    ctx.reply('✅ Заявка создана!');
    ctx.session = null;
  }
});

const WEBHOOK_URL = process.env.WEBHOOK_URL;
if (WEBHOOK_URL) {
  bot.telegram.setWebhook(`${WEBHOOK_URL}/bot`);
  app.use(bot.webhookCallback('/bot'));
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`CRM на порту ${PORT}`));
