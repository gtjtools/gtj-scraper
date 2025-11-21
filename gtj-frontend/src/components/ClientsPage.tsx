import { Building2, Calendar, Mail, Phone, Search } from 'lucide-react';
import { useState } from 'react';
import { Client, Quote } from '../lib/mock-data';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Input } from './ui/input';

interface ClientsPageProps {
  clients: Client[];
  quotes: Quote[];
  onSelectClient: (client: Client, clientQuotes: Quote[]) => void;
}

export function ClientsPage({
  clients,
  quotes,
  onSelectClient,
}: ClientsPageProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const getClientStats = (client: Client) => {
    const clientQuotes = quotes.filter((q) => q.client.id === client.id);
    const totalQuotes = clientQuotes.length;
    const acceptedQuotes = clientQuotes.filter(
      (q) => q.status === 'accepted'
    ).length;
    const totalRevenue = clientQuotes
      .filter((q) => q.status === 'accepted')
      .reduce((sum, q) => sum + q.totalPrice, 0);
    const lastQuoteDate =
      clientQuotes.length > 0
        ? new Date(
            Math.max(
              ...clientQuotes.map((q) => new Date(q.timestamp).getTime())
            )
          )
        : null;

    return { totalQuotes, acceptedQuotes, totalRevenue, lastQuoteDate };
  };

  const filteredClients = clients.filter(
    (client) =>
      client.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      client.company.toLowerCase().includes(searchQuery.toLowerCase()) ||
      client.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Clients</h1>
          <p className="text-muted-foreground mt-1">
            Manage your client relationships and view booking history
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search clients by name, company, or email..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Clients Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filteredClients.map((client) => {
          const stats = getClientStats(client);
          const clientQuotes = quotes.filter((q) => q.client.id === client.id);

          return (
            <Card
              key={client.id}
              className="p-6 hover:shadow-lg transition-shadow"
            >
              <div className="space-y-4">
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-semibold">{client.name}</h3>
                    <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
                      <Building2 className="h-3 w-3" />
                      <span>{client.company}</span>
                    </div>
                  </div>
                  {stats.totalQuotes > 0 && (
                    <Badge variant="secondary">
                      {stats.totalQuotes} quotes
                    </Badge>
                  )}
                </div>

                {/* Contact Info */}
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Mail className="h-3 w-3" />
                    <span className="truncate">{client.email}</span>
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Phone className="h-3 w-3" />
                    <span>{client.phone}</span>
                  </div>
                </div>

                {/* Stats */}
                {stats.totalQuotes > 0 && (
                  <div className="grid grid-cols-2 gap-3 pt-3 border-t">
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">
                        Accepted
                      </div>
                      <div className="font-semibold">
                        {stats.acceptedQuotes}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">
                        Revenue
                      </div>
                      <div className="font-semibold">
                        ${(stats.totalRevenue / 1000).toFixed(0)}k
                      </div>
                    </div>
                  </div>
                )}

                {stats.lastQuoteDate && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2 border-t">
                    <Calendar className="h-3 w-3" />
                    <span>
                      Last quote: {stats.lastQuoteDate.toLocaleDateString()}
                    </span>
                  </div>
                )}

                {/* Actions */}
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => onSelectClient(client, clientQuotes)}
                >
                  View Details
                </Button>
              </div>
            </Card>
          );
        })}
      </div>

      {filteredClients.length === 0 && (
        <Card className="p-12 text-center">
          <p className="text-muted-foreground">
            No clients found matching your search
          </p>
        </Card>
      )}
    </div>
  );
}
