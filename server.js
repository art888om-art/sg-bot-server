const { readFileSync } = require('fs');
const path = require('path');
const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());

const ENHANCED_SYSTEM = readFileSync(
  path.join(__dirname, 'prompts', 'starter-generator-consultant-prompt.md'),
  'utf8'
);

app.post('/chat', async (req, res) => {
  const { messages } = req.body;
  if (!messages) return res.status(400).json({ error: 'No messages' });

  if (!process.env.GEMINI_KEY) {
    return res.status(500).json({ error: 'GEMINI_KEY is not configured' });
  }

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${process.env.GEMINI_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system_instruction: { parts: [{ text: ENHANCED_SYSTEM }] },
          contents: messages.map((m) => ({
            role: m.role === 'assistant' ? 'model' : 'user',
            parts: [{ text: m.content }]
          })),
          generationConfig: { maxOutputTokens: 1000, temperature: 0.7 }
        })
      }
    );
    const data = await response.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || 'Помилка відповіді';
    res.json({ reply: text });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/', (req, res) => res.send('Bot server running'));
app.listen(process.env.PORT || 3000, () => console.log('Server started'));
