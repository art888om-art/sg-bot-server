import React from 'react';
import { Menu } from 'lucide-react';

export default function Navbar() {
  return (
    <header className="bg-white shadow-sm p-4 flex items-center justify-between md:justify-end">
      <button className="md:hidden p-1 rounded hover:bg-gray-200">
        <Menu className="w-6 h-6" />
      </button>
      <div className="text-sm text-gray-600">
        Менеджер: <span className="font-medium">Вы</span>
      </div>
    </header>
  );
}
