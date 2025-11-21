import { Quote } from '../lib/mock-data';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Clock, CheckCircle2, XCircle, Eye, FileText } from 'lucide-react';
import { TrustScoreGauge } from './TrustScoreGauge';

interface QuoteInboxProps {
  quotes: Quote[];
  onViewQuote?: (quote: Quote) => void;
  onAcceptQuote?: (quote: Quote) => void;
  onDeclineQuote?: (quote: Quote) => void;
}

export function QuoteInbox({ quotes, onViewQuote, onAcceptQuote, onDeclineQuote }: QuoteInboxProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  const getTimeRemaining = (expiresAt: string) => {
    const now = new Date();
    const expiry = new Date(expiresAt);
    const diff = expiry.getTime() - now.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    
    if (hours < 0) return 'Expired';
    if (hours < 24) return `${hours}h remaining`;
    const days = Math.floor(hours / 24);
    return `${days}d remaining`;
  };

  const getStatusBadge = (status: Quote['status']) => {
    const variants: Record<Quote['status'], { variant: 'default' | 'secondary' | 'outline' | 'destructive', label: string }> = {
      new: { variant: 'default', label: 'New' },
      reviewing: { variant: 'secondary', label: 'Reviewing' },
      accepted: { variant: 'outline', label: 'Accepted' },
      declined: { variant: 'destructive', label: 'Declined' }
    };
    
    const config = variants[status];
    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-4">
      {quotes.map((quote) => (
        <Card key={quote.id} className="p-6 hover:shadow-md transition-shadow">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-start gap-4 flex-1">
              <div className="flex-shrink-0">
                <TrustScoreGauge score={quote.aircraft.operator.trustScore} size="sm" />
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <h3 className="font-semibold mb-1">
                      {quote.aircraft.operator.name}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      {quote.aircraft.manufacturer} {quote.aircraft.model} ({quote.aircraft.tailNumber})
                    </p>
                  </div>
                  {getStatusBadge(quote.status)}
                </div>
                
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Route</p>
                    <p className="text-sm">{quote.route.departure} → {quote.route.arrival}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Flight Date</p>
                    <p className="text-sm">{formatDate(quote.date)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Passengers</p>
                    <p className="text-sm">{quote.passengers} pax</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Flight Time</p>
                    <p className="text-sm">{quote.flightTime} hours</p>
                  </div>
                </div>

                {quote.notes && (
                  <div className="mt-3 p-3 bg-muted/50 rounded-lg">
                    <p className="text-sm text-muted-foreground">{quote.notes}</p>
                  </div>
                )}
              </div>
            </div>

            <div className="text-right ml-4">
              <p className="text-2xl font-bold text-[#335cff] mb-1">
                ${quote.totalPrice.toLocaleString()}
              </p>
              <div className="flex items-center gap-1 text-xs text-muted-foreground justify-end">
                <Clock className="h-3 w-3" />
                <span>{getTimeRemaining(quote.expiresAt)}</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Received {formatTime(quote.timestamp)}
              </p>
            </div>
          </div>

          <div className="flex gap-2 mt-4 pt-4 border-t flex-wrap">
            <Button 
              variant="outline" 
              size="sm" 
              className="gap-2"
              onClick={() => onViewQuote?.(quote)}
            >
              <Eye className="h-4 w-4" />
              View Details
            </Button>
            
            {quote.status === 'new' || quote.status === 'reviewing' ? (
              <>
                <Button 
                  variant="default" 
                  size="sm" 
                  className="gap-2 bg-[#335cff] hover:bg-[#2847cc]"
                  onClick={() => onAcceptQuote?.(quote)}
                >
                  <CheckCircle2 className="h-4 w-4" />
                  Accept Quote
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="gap-2"
                  onClick={() => onDeclineQuote?.(quote)}
                >
                  <XCircle className="h-4 w-4" />
                  Decline
                </Button>
              </>
            ) : null}
          </div>
        </Card>
      ))}
    </div>
  );
}
