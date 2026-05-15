import React, { useEffect, useState } from 'react';

const STATUSES = ['new', 'in_progress', 'sold', 'rejected'];
const STATUS_LABELS = {
  new: 'Новый',
  in_progress: 'В работе',
  sold: 'Продан',
  rejected: 'Отказ',
};

export default function Deals() {
  const [deals, setDeals] = useState([]);

  const fetchDeals = () => {
    fetch('/api/deals')
      .then(r => r.json())
      .then(setDeals)
      .catch(console.error);
  };

  useEffect(fetchDeals, []);

  const updateStatus = (id, status) => {
    fetch(`/api/deals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).then(fetchDeals);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Заявки</h1>
      <div className="bg-white rounded-xl shadow overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Клиент</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Товар</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Источник</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Статус</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {deals.map(deal => (
              <tr key={deal.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="font-medium">{deal.client_phone || '—'}</div>
                </td>
                <td className="px-4 py-3 text-sm">{deal.product_name || '—'}</td>
                <td className="px-4 py-3 text-sm">{deal.source}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                    deal.status === 'sold' ? 'bg-green-100 text-green-800' :
                    deal.status === 'rejected' ? 'bg-red-100 text-red-800' :
                    deal.status === 'in_progress' ? 'bg-blue-100 text-blue-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {STATUS_LABELS[deal.status] || deal.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <select
                    className="text-xs border rounded px-2 py-1"
                    value={deal.status}
                    onChange={(e) => updateStatus(deal.id, e.target.value)}
                  >
                    {STATUSES.map(s => (
                      <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
