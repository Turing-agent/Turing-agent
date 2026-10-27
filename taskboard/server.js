const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 80;
const APP_VERSION = process.env.APP_VERSION || 'v1.0.0';

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// In-memory tasks list
let tasks = [
  { id: 1, title: 'Review pull requests' },
  { id: 2, title: 'Prepare release notes' }
];

// Sanity check endpoint
app.get('/version', (req, res) => {
  res.send(APP_VERSION);
});

// HTML Pages
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/settings', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'settings.html'));
});

// Task APIs
app.get('/api/tasks', (req, res) => {
  res.json({ tasks });
});

app.post('/api/tasks', (req, res) => {
  const { title } = req.body;
  if (!title) {
    return res.status(400).json({ error: 'Title is required' });
  }
  const newTask = { id: tasks.length + 1, title };
  tasks.push(newTask);
  res.status(201).json(newTask);
});

// Account Deletion API
app.post('/api/delete-account', (req, res) => {
  if (APP_VERSION === 'v1.1.0') {
    // Planted deterministic bug
    return res.status(500).json({
      error: 'NullReference: user.profile is undefined'
    });
  }

  // Working version v1.0.0
  res.status(200).json({
    success: true,
    message: 'Account deleted successfully'
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`TaskBoard [${APP_VERSION}] listening on port ${PORT}`);
});
