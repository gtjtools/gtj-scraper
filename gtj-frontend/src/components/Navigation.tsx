import { Inbox, FileText, Users, TrendingUp, PlaneTakeoff, Radio, Building2 } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';

interface NavigationProps {
  currentPage: string;
  onNavigate: (page: string) => void;
  draftQuotesCount?: number;
  trackedFlightsCount?: number;
}

export function Navigation({ currentPage, onNavigate, draftQuotesCount = 0, trackedFlightsCount = 0 }: NavigationProps) {
  const navItems = [
    { id: 'inbox', label: 'Inbox', icon: Inbox },
    { id: 'track', label: 'Track', icon: Radio, badge: trackedFlightsCount },
    { id: 'quotes', label: 'Quotes', icon: FileText, badge: draftQuotesCount },
    { id: 'clients', label: 'Clients', icon: Users },
    { id: 'operators', label: 'Operators', icon: Building2 },
    { id: 'financials', label: 'Financials', icon: TrendingUp },
  ];

  return (
    <nav className="flex items-center justify-between gap-6">
      <div className="flex items-center gap-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors relative ${
                isActive
                  ? 'bg-white/20 text-white'
                  : 'text-white/70 hover:text-white hover:bg-white/10'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
              {item.badge && item.badge > 0 && (
                <Badge variant="secondary" className="ml-1 bg-white/20 text-white px-1.5 py-0 h-5 min-w-5 flex items-center justify-center">
                  {item.badge}
                </Badge>
              )}
            </button>
          );
        })}
      </div>
      
      <div className="flex items-center gap-2">
        <Button
          onClick={() => onNavigate('new-flight')}
          className="bg-[#335cff] hover:bg-[#2847cc] text-white gap-2 rounded-[10px]"
        >
          <PlaneTakeoff className="h-4 w-4" />
          Search for Tails
        </Button>
      </div>
    </nav>
  );
}
