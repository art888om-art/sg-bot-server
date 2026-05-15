import React, { useEffect, useState } from 'react';
import { LayoutDashboard, TrendingUp, Users, DollarSign } from 'lucide-react';

export default function Dashboard() {
  const [stats, setStats] = useState({ total_deals: 0, sold_deals: 0, new_clients: 0 });

  useEffect(() => {
    fetch('/api/analytics/dashboard')
      .then(r => r.json())
      .then(setStats)
      .catch(console.error);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Дашборд</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={LayoutDashboard} label="Всего заявок" value={stats.total_deals} color="bg-blue-500" />
        <StatCard icon={TrendingUp} label="Продаж" value={stats.sold_deals} color="bg-green-500" />
        <StatCard icon={Users} label="Новых клиентов (7 дн.)" value={stats.new_clients} color="bg-purple-500" />
        <StatCard icon={DollarSign} label="Активность" value="—" color="bg-orange-500" />
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="bg-white rounded-xl shadow p-4 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${color} text-white`}>
        <Icon className="w-6 h-6" />
      </div>
      <div>
        <p className="text-gray-500 text-sm">{label}</p>
        <p className="text-2xl font-semibold">{value}</p>
      </div>
    </div>
  );
}
