import { Client, Quote } from '../lib/mock-data';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet';
import { QuoteInbox } from './QuoteInbox';
import { User, Building2, Mail, Phone } from 'lucide-react';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';

interface ClientQuotesModalProps {
  client: Client | null;
  quotes: Quote[];
  isOpen: boolean;
  onClose: () => void;
  onViewQuote: (quote: Quote) => void;
  onAcceptQuote: (quote: Quote) => void;
  onDeclineQuote: (quote: Quote) => void;
}

export function ClientQuotesModal({
  client,
  quotes,
  isOpen,
  onClose,
  onViewQuote,
  onAcceptQuote,
  onDeclineQuote
}: ClientQuotesModalProps) {
  if (!client) return null;

  const newQuotesCount = quotes.filter(q => q.status === 'new').length;
  const firstQuote = quotes[0];

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="right" className="w-full sm:max-w-3xl p-0 flex flex-col">
        <SheetHeader className="border-b px-6 py-4">
          <SheetTitle>Quotes for {client.name}</SheetTitle>
        </SheetHeader>
        
        <ScrollArea className="flex-1 px-6">

          {/* Client Info Card */}
          <div className="bg-muted/50 rounded-lg p-4 my-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-10 h-10 rounded-full bg-[#335cff]/10 flex items-center justify-center">
                    <User className="h-5 w-5 text-[#335cff]" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{client.name}</h3>
                    <div className="flex items-center gap-1 text-sm text-muted-foreground">
                      <Building2 className="h-3 w-3" />
                      <span>{client.company}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Mail className="h-3 w-3" />
                  <span>{client.email}</span>
                </div>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Phone className="h-3 w-3" />
                  <span>{client.phone}</span>
                </div>
              </div>
            </div>

            {firstQuote && (
              <div className="mt-4 pt-4 border-t border-border">
                <div className="flex items-center gap-4 text-sm flex-wrap">
                  <div>
                    <span className="text-muted-foreground">Route: </span>
                    <span className="font-medium">
                      {firstQuote.route.departure} → {firstQuote.route.arrival}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Flight Date: </span>
                    <span className="font-medium">
                      {new Date(firstQuote.date).toLocaleDateString('en-US', { 
                        month: 'short', 
                        day: 'numeric', 
                        year: 'numeric' 
                      })}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Passengers: </span>
                    <span className="font-medium">{firstQuote.passengers}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Quotes Header */}
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">
              {quotes.length} {quotes.length === 1 ? 'Quote' : 'Quotes'} from Operators
            </h3>
            {newQuotesCount > 0 && (
              <Badge variant="default" className="bg-[#335cff]">
                {newQuotesCount} new
              </Badge>
            )}
          </div>

          {/* Quotes List */}
          <div className="pb-6">
            <QuoteInbox
              quotes={quotes}
              onViewQuote={onViewQuote}
              onAcceptQuote={onAcceptQuote}
              onDeclineQuote={onDeclineQuote}
            />
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
