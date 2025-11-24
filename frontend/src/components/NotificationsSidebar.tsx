import { Notification } from '../lib/mock-data';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import { Separator } from './ui/separator';
import { 
  AlertTriangle, 
  TrendingDown, 
  CheckCircle2, 
  Inbox,
  Check,
  Plane,
  Clock
} from 'lucide-react';
import { cn } from './ui/utils';

interface NotificationsSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: Notification[];
  onMarkAsRead: (notificationId: string) => void;
  onMarkAllAsRead: () => void;
  onNotificationClick: (notification: Notification) => void;
}

export function NotificationsSidebar({
  isOpen,
  onClose,
  notifications,
  onMarkAsRead,
  onMarkAllAsRead,
  onNotificationClick
}: NotificationsSidebarProps) {
  const unreadCount = notifications.filter(n => !n.isRead).length;

  const getNotificationIcon = (type: Notification['type']) => {
    switch (type) {
      case 'aog-incident':
        return <AlertTriangle className="h-5 w-5 text-red-600" />;
      case 'tripscore-generated':
        return <CheckCircle2 className="h-5 w-5 text-green-600" />;
      case 'tripscore-low':
        return <TrendingDown className="h-5 w-5 text-amber-600" />;
      case 'quote-received':
        return <Inbox className="h-5 w-5 text-blue-600" />;
      case 'booking-confirmed':
        return <Plane className="h-5 w-5 text-green-600" />;
    }
  };

  const getNotificationColor = (type: Notification['type']) => {
    switch (type) {
      case 'aog-incident':
        return 'bg-red-50 border-red-200';
      case 'tripscore-generated':
        return 'bg-green-50 border-green-200';
      case 'tripscore-low':
        return 'bg-amber-50 border-amber-200';
      case 'quote-received':
        return 'bg-blue-50 border-blue-200';
      case 'booking-confirmed':
        return 'bg-green-50 border-green-200';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.isRead) {
      onMarkAsRead(notification.id);
    }
    onNotificationClick(notification);
    onClose();
  };

  const sortedNotifications = [...notifications].sort((a, b) => 
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2">
              Notifications
              {unreadCount > 0 && (
                <Badge className="bg-[#335cff] text-white">
                  {unreadCount}
                </Badge>
              )}
            </SheetTitle>
            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onMarkAllAsRead}
                className="text-sm"
              >
                <Check className="h-4 w-4 mr-2" />
                Mark all read
              </Button>
            )}
          </div>
        </SheetHeader>

        <Separator className="my-4" />

        {notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="rounded-full bg-slate-100 p-6 mb-4">
              <Inbox className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="font-semibold mb-2">No notifications</h3>
            <p className="text-sm text-muted-foreground max-w-xs">
              You're all caught up! Notifications will appear here when there's something new.
            </p>
          </div>
        ) : (
          <ScrollArea className="h-[calc(100vh-120px)] pr-4">
            <div className="space-y-3">
              {sortedNotifications.map((notification) => {
                const NotificationIcon = getNotificationIcon(notification.type);
                const colorClass = getNotificationColor(notification.type);

                return (
                  <button
                    key={notification.id}
                    onClick={() => handleNotificationClick(notification)}
                    className={cn(
                      "w-full text-left p-4 rounded-lg border transition-all hover:shadow-md",
                      colorClass,
                      !notification.isRead && "ring-2 ring-offset-2 ring-[#335cff]/20"
                    )}
                  >
                    <div className="flex gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        {NotificationIcon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <p className={cn(
                            "text-sm",
                            !notification.isRead && "font-semibold"
                          )}>
                            {notification.title}
                          </p>
                          {!notification.isRead && (
                            <div className="flex-shrink-0 h-2 w-2 rounded-full bg-[#335cff] mt-1" />
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mb-2 break-words">
                          {notification.description}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {formatTimestamp(notification.timestamp)}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}
