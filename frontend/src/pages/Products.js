import React, { useEffect, useState } from 'react';

export default function Products() {
  const [products, setProducts] = useState([]);

  useEffect(() => {
    fetch('/api/products')
      .then(r => r.json())
      .then(setProducts);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Товары</h1>
      <div className="bg-white rounded-xl shadow p-4">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Тип</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Бренд</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Модель</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Цена</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Кол-во</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {products.map(p => (
              <tr key={p.id}>
                <td className="px-4 py-3 text-sm">{p.type}</td>
                <td className="px-4 py-3 text-sm">{p.brand}</td>
                <td className="px-4 py-3 text-sm">{p.model}</td>
                <td className="px-4 py-3 text-sm">{p.price} ₽</td>
                <td className="px-4 py-3 text-sm">{p.stock_quantity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
