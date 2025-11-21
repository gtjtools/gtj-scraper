import { Quote } from '../lib/mock-data';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Eye, MessageSquare, Calendar } from 'lucide-react';

interface CurrentQuotesProps {
  quotes: Quote[];
  onViewQuote?: (quote: Quote) => void;
}

export function CurrentQuotes({ quotes, onViewQuote }: CurrentQuotesProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getStatusColor = (status: Quote['status']) => {
    const colors: Record<Quote['status'], string> = {
      new: 'bg-blue-500',
      reviewing: 'bg-yellow-500',
      accepted: 'bg-green-500',
      declined: 'bg-red-500'
    };
    return colors[status];
  };

  // Group quotes by status
  const activeQuotes = quotes.filter(q => q.status === 'new' || q.status === 'reviewing');
  const completedQuotes = quotes.filter(q => q.status === 'accepted' || q.status === 'declined');

  return (
    <div className="space-y-6">
      {/* Active Quotes */}
      {activeQuotes.length > 0 && (
        <div>
          <h3 className="font-semibold mb-3 text-sm text-muted-foreground uppercase tracking-wide">
            Active ({activeQuotes.length})
          </h3>
          <div className="space-y-3">
            {activeQuotes.map((quote) => (
              <Card key={quote.id} className="p-4 hover:shadow-md transition-shadow">
                <div className="flex items-center gap-3">
                  <div className={`w-1 h-16 rounded-full ${getStatusColor(quote.status)}`} />
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="font-semibold text-sm">
                          {quote.route.departure} → {quote.route.arrival}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {quote.aircraft.manufacturer} {quote.aircraft.model}
                        </p>
                      </div>
                      <Badge variant="secondary" className="text-xs">
                        {quote.status}
                      </Badge>
                    </div>
                    
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        <span>{formatDate(quote.date)}</span>
                      </div>
                      <span>•</span>
                      <span className="font-semibold text-foreground">
                        ${quote.totalPrice.toLocaleString()}
                      </span>
                    </div>
                  </div>

                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => onViewQuote?.(quote)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Completed Quotes */}
      {completedQuotes.length > 0 && (
        <div>
          <h3 className="font-semibold mb-3 text-sm text-muted-foreground uppercase tracking-wide">
            Completed ({completedQuotes.length})
          </h3>
          <div className="space-y-3">
            {completedQuotes.map((quote) => (
              <Card key={quote.id} className="p-4 opacity-75 hover:opacity-100 transition-opacity">
                <div className="flex items-center gap-3">
                  <div className={`w-1 h-16 rounded-full ${getStatusColor(quote.status)}`} />
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="font-semibold text-sm">
                          {quote.route.departure} → {quote.route.arrival}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {quote.aircraft.manufacturer} {quote.aircraft.model}
                        </p>
                      </div>
                      <Badge 
                        variant={quote.status === 'accepted' ? 'outline' : 'destructive'}
                        className="text-xs"
                      >
                        {quote.status}
                      </Badge>
                    </div>
                    
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        <span>{formatDate(quote.date)}</span>
                      </div>
                      <span>•</span>
                      <span className="font-semibold text-foreground">
                        ${quote.totalPrice.toLocaleString()}
                      </span>
                    </div>
                  </div>

                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => onViewQuote?.(quote)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {quotes.length === 0 && (
        <div className="text-center py-12">
          <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-3 opacity-50" />
          <p className="text-muted-foreground">No quotes yet</p>
          <p className="text-sm text-muted-foreground mt-1">
            Start a search to request quotes from operators
          </p>
        </div>
      )}
    </div>
  );
}
