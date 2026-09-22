// Installable shell, deliberately no Cache API, IndexedDB, or offline response.
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
// No fetch handler: every request goes to the network; clinical state never leaves the page.
