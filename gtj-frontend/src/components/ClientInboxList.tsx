import { Client, Quote } from '../lib/mock-data';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { ChevronRight, User, Building2, Calendar } from 'lucide-react';

interface ClientInboxListProps {
  quotes: Quote[];
  onSelectClient: (client: Client, clientQuotes: Quote[]) => void;
}

export function ClientInboxList({ quotes, onSelectClient }: ClientInboxListProps) {
  // Group quotes by client
  const clientQuotesMap = quotes.reduce((acc, quote) => {
    const clientId = quote.client.id;
    if (!acc[clientId]) {
      acc[clientId] = {
        client: quote.client,
        quotes: [],
        latestDate: quote.timestamp
      };
    }
    acc[clientId].quotes.push(quote);
    if (quote.timestamp > acc[clientId].latestDate) {
      acc[clientId].latestDate = quote.timestamp;
    }
    return acc;
  }, {} as Record<string, { client: Client; quotes: Quote[]; latestDate: string }>);

  // Convert to array and sort by latest quote date
  const clientGroups = Object.values(clientQuotesMap).sort(
    (a, b) => new Date(b.latestDate).getTime() - new Date(a.latestDate).getTime()
  );

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  const getNewQuotesCount = (clientQuotes: Quote[]) => {
    return clientQuotes.filter(q => q.status === 'new').length;
  };

  return (
    <div className="space-y-3">
      {clientGroups.map(({ client, quotes: clientQuotes, latestDate }) => {
        const newCount = getNewQuotesCount(clientQuotes);
        const firstQuote = clientQuotes[0];
        
        return (
          <Card 
            key={client.id} 
            className="p-4 hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => onSelectClient(client, clientQuotes)}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-3 mb-2">
                  <div className="flex-shrink-0 w-10 h-10 rounded-full bg-[#335cff]/10 flex items-center justify-center">
                    <User className="h-5 w-5 text-[#335cff]" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold truncate">{client.name}</h3>
                      {newCount > 0 && (
                        <Badge variant="default" className="bg-[#335cff] text-xs">
                          {newCount} new
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                      <Building2 className="h-3 w-3" />
                      <span className="truncate">{client.company}</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Calendar className="h-3 w-3" />
                      <span>
                        Latest: {formatDate(latestDate)} at {formatTime(latestDate)}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="ml-13 pl-3 border-l-2 border-muted">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Route:</span>
                    <span>{firstQuote.route.departure} → {firstQuote.route.arrival}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                    <span>{clientQuotes.length} {clientQuotes.length === 1 ? 'quote' : 'quotes'} from operators</span>
                  </div>
                </div>
              </div>

              <Button 
                variant="ghost" 
                size="sm"
                className="flex-shrink-0"
              >
                <ChevronRight className="h-5 w-5" />
              </Button>
            </div>
          </Card>
        );
      })}

      {clientGroups.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <p>No quotes in inbox</p>
        </div>
      )}
    </div>
  );
}
