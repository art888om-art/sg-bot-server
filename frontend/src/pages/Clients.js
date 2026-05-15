import React, { useEffect, useState } from 'react';

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetch(`/api/clients?search=${encodeURIComponent(search)}`)
      .then(r => r.json())
      .then(setClients);
  }, [search]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Клиенты</h1>
      <div className="bg-white rounded-xl shadow p-4">
        <input
          type="text"
          placeholder="Поиск по телефону или имени..."
          className="border rounded px-3 py-2 w-full mb-4"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map(client => (
            <div key={client.id} className="border rounded-lg p-3">
              <p className="font-medium">{client.full_name || 'Без имени'}</p>
              <p className="text-sm text-gray-500">{client.phone}</p>
              <p className="text-xs text-gray-400">{new Date(client.created_at).toLocaleDateString()}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
