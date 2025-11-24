import { Activity } from '../lib/mock-data';
import { Inbox, Send, CheckCircle2, Bookmark, Star } from 'lucide-react';

interface ActivityFeedProps {
  activities: Activity[];
}

export function ActivityFeed({ activities }: ActivityFeedProps) {
  const getIcon = (iconName: Activity['icon']) => {
    const icons = {
      inbox: Inbox,
      send: Send,
      check: CheckCircle2,
      bookmark: Bookmark,
      star: Star
    };
    
    const Icon = icons[iconName];
    return <Icon className="h-4 w-4" />;
  };

  const getIconColor = (type: Activity['type']) => {
    const colors: Record<Activity['type'], string> = {
      quote_received: 'bg-blue-100 text-blue-600',
      quote_sent: 'bg-purple-100 text-purple-600',
      booking_confirmed: 'bg-green-100 text-green-600',
      search_saved: 'bg-yellow-100 text-yellow-600',
      operator_reviewed: 'bg-orange-100 text-orange-600'
    };
    return colors[type];
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / (1000 * 60));
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="space-y-4">
      {activities.map((activity, index) => (
        <div key={activity.id} className="flex gap-3">
          {/* Timeline */}
          <div className="flex flex-col items-center">
            <div className={`rounded-full p-2 ${getIconColor(activity.type)}`}>
              {getIcon(activity.icon)}
            </div>
            {index < activities.length - 1 && (
              <div className="w-px h-full bg-border mt-2" />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 pb-6">
            <div className="flex items-start justify-between gap-2 mb-1">
              <h4 className="font-semibold text-sm">{activity.title}</h4>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {formatTimestamp(activity.timestamp)}
              </span>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              {activity.description}
            </p>
            
            {activity.metadata && (
              <div className="flex flex-wrap gap-2 text-xs">
                {activity.metadata.aircraft && (
                  <span className="px-2 py-1 bg-muted rounded">
                    {activity.metadata.aircraft}
                  </span>
                )}
                {activity.metadata.operator && (
                  <span className="px-2 py-1 bg-muted rounded">
                    {activity.metadata.operator}
                  </span>
                )}
                {activity.metadata.route && (
                  <span className="px-2 py-1 bg-muted rounded">
                    {activity.metadata.route}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Empty State */}
      {activities.length === 0 && (
        <div className="text-center py-12">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-muted rounded-full mb-3">
            <Inbox className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-muted-foreground">No recent activity</p>
        </div>
      )}
    </div>
  );
}
