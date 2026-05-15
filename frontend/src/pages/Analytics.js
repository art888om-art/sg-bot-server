import React, { useEffect, useState } from 'react';

export default function Analytics() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('/api/analytics/dashboard')
      .then(r => r.json())
      .then(setData);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Аналитика</h1>
      <div className="bg-white rounded-xl shadow p-6">
        {data ? (
          <div className="grid grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-3xl font-bold">{data.total_deals}</div>
              <div className="text-gray-500">Всего заявок</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">{data.sold_deals}</div>
              <div className="text-gray-500">Продаж</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">{data.new_clients}</div>
              <div className="text-gray-500">Новых клиентов</div>
            </div>
          </div>
        ) : (
          <p>Загрузка...</p>
        )}
      </div>
    </div>
  );
}
