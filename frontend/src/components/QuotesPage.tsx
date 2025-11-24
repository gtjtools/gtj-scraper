import { useState } from 'react';
import { Quote } from '../lib/mock-data';
import { Card } from './ui/card';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { Search, Filter, Plane, Calendar, Users, DollarSign, Clock, ChevronDown, ChevronUp, MapPin, ArrowRight, Building2, User, Send, FileText, Check, Plus } from 'lucide-react';
import { TrustScoreGauge } from './TrustScoreGauge';

interface QuotesPageProps {
  quotes: Quote[];
  onViewQuote: (quote: Quote) => void;
  onViewDetails?: (quote: Quote) => void;
}

export interface RouteQuoteGroup {
  route: {
    departure: string;
    arrival: string;
  };
  date: string;
  passengers: number;
  client: {
    name: string;
    company: string;
  };
  quotes: Quote[];
  lowestPrice: number;
  averagePrice: number;
  pendingCount: number;
  acceptedCount: number;
  declinedCount: number;
}

export function QuotesPage({ quotes, onViewQuote, onViewDetails }: QuotesPageProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [expandedRoutes, setExpandedRoutes] = useState<Set<string>>(new Set());

  // Group quotes by route + date
  const groupQuotesByRoute = (quotesToGroup: Quote[]): RouteQuoteGroup[] => {
    const routeMap = new Map<string, RouteQuoteGroup>();

    quotesToGroup.forEach(quote => {
      // Skip quotes with missing required data
      if (!quote.route || !quote.client) return;
      
      const routeKey = `${quote.route.departure || 'TBD'}-${quote.route.arrival || 'TBD'}-${quote.date || 'TBD'}`;
      
      if (!routeMap.has(routeKey)) {
        routeMap.set(routeKey, {
          route: quote.route,
          date: quote.date || new Date().toISOString(),
          passengers: quote.passengers || 0,
          client: {
            name: quote.client.name || 'Unknown',
            company: quote.client.company || 'Unknown'
          },
          quotes: [],
          lowestPrice: Infinity,
          averagePrice: 0,
          pendingCount: 0,
          acceptedCount: 0,
          declinedCount: 0
        });
      }

      const group = routeMap.get(routeKey)!;
      group.quotes.push(quote);
      
      // Calculate price from aircraftPricing if available, otherwise use legacy totalPrice
      const quotePrice = quote.aircraftPricing && quote.aircraftPricing.length > 0
        ? Math.min(...quote.aircraftPricing.map(p => p.myPrice))
        : (quote.totalPrice || 0);
      
      if (quotePrice > 0 && quotePrice < group.lowestPrice) {
        group.lowestPrice = quotePrice;
      }
      
      if (quote.status === 'draft' || quote.status === 'sent') {
        group.pendingCount++;
      } else if (quote.status === 'accepted') {
        group.acceptedCount++;
      } else if (quote.status === 'declined' || quote.status === 'expired') {
        group.declinedCount++;
      }
    });

    // Calculate average prices
    routeMap.forEach(group => {
      const prices = group.quotes.map(q => {
        if (q.aircraftPricing && q.aircraftPricing.length > 0) {
          return Math.min(...q.aircraftPricing.map(p => p.myPrice));
        }
        return q.totalPrice || 0;
      }).filter(p => p > 0);
      
      if (prices.length > 0) {
        const totalPrice = prices.reduce((sum, p) => sum + p, 0);
        group.averagePrice = Math.round(totalPrice / prices.length);
      }
    });

    // Sort by date (most recent first)
    return Array.from(routeMap.values()).sort((a, b) => {
      return new Date(b.date).getTime() - new Date(a.date).getTime();
    });
  };

  const filteredQuotes = quotes.filter(quote => {
    // Get aircraft for search - handle both legacy (aircraft) and new (aircraftOptions) structure
    const aircraftToSearch = quote.aircraft 
      ? [quote.aircraft] 
      : (quote.aircraftOptions || []);
    
    const matchesSearch = 
      aircraftToSearch.some(aircraft => 
        aircraft && aircraft.type && aircraft.operator &&
        (aircraft.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
        aircraft.operator.name.toLowerCase().includes(searchQuery.toLowerCase()))
      ) ||
      quote.route?.departure?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      quote.route?.arrival?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      quote.client?.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (quote.title || '').toLowerCase().includes(searchQuery.toLowerCase());

    if (activeTab === 'all') return matchesSearch;
    if (activeTab === 'draft') return matchesSearch && quote.status === 'draft';
    if (activeTab === 'sent') return matchesSearch && quote.status === 'sent';
    if (activeTab === 'accepted') return matchesSearch && quote.status === 'accepted';
    if (activeTab === 'declined') return matchesSearch && quote.status === 'declined';
    if (activeTab === 'expired') return matchesSearch && quote.status === 'expired';
    
    return matchesSearch;
  });

  const routeGroups = groupQuotesByRoute(filteredQuotes);

  const toggleRoute = (routeKey: string) => {
    const newExpanded = new Set(expandedRoutes);
    if (newExpanded.has(routeKey)) {
      newExpanded.delete(routeKey);
    } else {
      newExpanded.add(routeKey);
    }
    setExpandedRoutes(newExpanded);
  };

  const toggleAllRoutes = () => {
    if (expandedRoutes.size === routeGroups.length) {
      setExpandedRoutes(new Set());
    } else {
      setExpandedRoutes(new Set(routeGroups.map((g, i) => `${g.route.departure}-${g.route.arrival}-${g.date}`)));
    }
  };



  const getStatusColor = (status: Quote['status']) => {
    switch (status) {
      case 'draft': return 'bg-gray-400';
      case 'sent': return 'bg-blue-500';
      case 'accepted': return 'bg-green-500';
      case 'declined': return 'bg-red-400';
      case 'expired': return 'bg-orange-400';
      default: return 'bg-gray-400';
    }
  };

  const getStatusLabel = (status: Quote['status']) => {
    switch (status) {
      case 'draft': return 'Draft';
      case 'sent': return 'Sent';
      case 'accepted': return 'Accepted';
      case 'declined': return 'Declined';
      case 'expired': return 'Expired';
      default: return status;
    }
  };

  const draftCount = quotes.filter(q => q.status === 'draft').length;
  const sentCount = quotes.filter(q => q.status === 'sent').length;
  const acceptedCount = quotes.filter(q => q.status === 'accepted').length;
  const declinedCount = quotes.filter(q => q.status === 'declined').length;
  const expiredCount = quotes.filter(q => q.status === 'expired').length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Client Quotes</h1>
          <p className="text-muted-foreground mt-1">
            Quotes for your clients organized by route • {routeGroups.length} {routeGroups.length === 1 ? 'route' : 'routes'} • {filteredQuotes.length} total quotes
          </p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={toggleAllRoutes}
          >
            {expandedRoutes.size === routeGroups.length ? 'Collapse All' : 'Expand All'}
          </Button>
          <Button variant="outline" className="gap-2">
            <Filter className="h-4 w-4" />
            Filter
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search by route, operator, aircraft, or client..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all">
            All ({quotes.length})
          </TabsTrigger>
          <TabsTrigger value="draft">
            Draft ({draftCount})
          </TabsTrigger>
          <TabsTrigger value="sent">
            Sent ({sentCount})
          </TabsTrigger>
          <TabsTrigger value="accepted">
            Accepted ({acceptedCount})
          </TabsTrigger>
          <TabsTrigger value="declined">
            Declined ({declinedCount})
          </TabsTrigger>
        </TabsList>

        <TabsContent value={activeTab} className="mt-6">
          <div className="space-y-4">
            {routeGroups.map((group) => {
              const routeKey = `${group.route.departure}-${group.route.arrival}-${group.date}`;
              const isExpanded = expandedRoutes.has(routeKey);
              
              return (
                <Card key={routeKey} className="overflow-hidden">
                  {/* Route Header */}
                  <Collapsible 
                    open={isExpanded}
                    onOpenChange={() => toggleRoute(routeKey)}
                  >
                    <CollapsibleTrigger asChild>
                      <div className="p-6 cursor-pointer hover:bg-muted/30 transition-colors">
                        {/* Client Header */}
                        <div className="flex items-center gap-3 mb-4 pb-4 border-b">
                          <div className="w-10 h-10 rounded-full bg-[#335cff]/10 flex items-center justify-center flex-shrink-0">
                            <User className="h-5 w-5 text-[#335cff]" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-semibold truncate">{group.client.name}</p>
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              <Building2 className="h-3 w-3" />
                              <span className="truncate">{group.client.company}</span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4 flex-1">
                            {/* Route Visual */}
                            <div className="flex items-center gap-3 bg-gradient-to-r from-[#335cff]/10 to-transparent p-4 rounded-lg flex-1 max-w-md">
                              <div className="flex-1">
                                <p className="text-xs text-muted-foreground mb-1">From</p>
                                <p className="font-semibold">{group.route.departure}</p>
                              </div>
                              <div className="flex-shrink-0">
                                <div className="w-8 h-8 rounded-full bg-[#335cff] flex items-center justify-center">
                                  <Plane className="h-4 w-4 text-white rotate-90" />
                                </div>
                              </div>
                              <div className="flex-1 text-right">
                                <p className="text-xs text-muted-foreground mb-1">To</p>
                                <p className="font-semibold">{group.route.arrival}</p>
                              </div>
                            </div>

                            {/* Flight Details */}
                            <div className="hidden md:flex items-center gap-4">
                              <div>
                                <p className="text-xs text-muted-foreground">Date</p>
                                <p className="font-medium">
                                  {new Date(group.date).toLocaleDateString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric',
                                    year: 'numeric'
                                  })}
                                </p>
                              </div>
                              <div>
                                <p className="text-xs text-muted-foreground">Passengers</p>
                                <p className="font-medium">{group.passengers}</p>
                              </div>
                              <div>
                                <p className="text-xs text-muted-foreground">Quotes</p>
                                <p className="font-medium">{group.quotes.length}</p>
                              </div>
                            </div>

                            {/* Stats */}
                            <div className="hidden lg:flex items-center gap-6 mr-8">
                              {group.pendingCount > 0 && (
                                <div className="text-center">
                                  <p className="text-xl font-bold text-blue-600">{group.pendingCount}</p>
                                  <p className="text-xs text-muted-foreground">Pending</p>
                                </div>
                              )}
                              {group.acceptedCount > 0 && (
                                <div className="text-center">
                                  <p className="text-xl font-bold text-green-600">{group.acceptedCount}</p>
                                  <p className="text-xs text-muted-foreground">Accepted</p>
                                </div>
                              )}
                              {group.declinedCount > 0 && (
                                <div className="text-center">
                                  <p className="text-xl font-bold text-gray-400">{group.declinedCount}</p>
                                  <p className="text-xs text-muted-foreground">Declined</p>
                                </div>
                              )}
                              <div className="text-center border-l pl-6">
                                <p className="text-xl font-bold text-[#335cff]">
                                  ${group.lowestPrice.toLocaleString()}
                                </p>
                                <p className="text-xs text-muted-foreground">Lowest Price</p>
                              </div>
                            </div>
                          </div>

                          {/* Expand Icon */}
                          <div className="flex-shrink-0 ml-4">
                            {isExpanded ? (
                              <ChevronUp className="h-5 w-5 text-muted-foreground" />
                            ) : (
                              <ChevronDown className="h-5 w-5 text-muted-foreground" />
                            )}
                          </div>
                        </div>

                        {/* Mobile Stats */}
                        <div className="flex md:hidden items-center gap-4 mt-4 pt-4 border-t">
                          <div className="text-center flex-1">
                            <p className="text-xs text-muted-foreground">Date</p>
                            <p className="font-medium text-sm">
                              {new Date(group.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                            </p>
                          </div>
                          <div className="text-center flex-1">
                            <p className="text-xs text-muted-foreground">Quotes</p>
                            <p className="font-medium text-sm">{group.quotes.length}</p>
                          </div>
                          <div className="text-center flex-1 border-l">
                            <p className="text-xs text-muted-foreground">From</p>
                            <p className="font-bold text-[#335cff] text-sm">
                              ${group.lowestPrice.toLocaleString()}
                            </p>
                          </div>
                        </div>
                      </div>
                    </CollapsibleTrigger>

                    {/* Route Quotes */}
                    <CollapsibleContent>
                      <div className="border-t bg-muted/20">
                        <div className="p-4 space-y-3">
                          {group.quotes.map((quote) => {
                            // Get first aircraft for display (handle both legacy and new structure)
                            const displayAircraft = quote.aircraft || 
                              (quote.aircraftOptions && quote.aircraftOptions.length > 0 ? quote.aircraftOptions[0] : null);
                            
                            // Get price from aircraftPricing if available, otherwise use legacy totalPrice
                            const displayPrice = quote.aircraftPricing && quote.aircraftPricing.length > 0
                              ? Math.min(...quote.aircraftPricing.map(p => p.myPrice))
                              : (quote.totalPrice || 0);
                            
                            // Skip quotes with no aircraft data
                            if (!displayAircraft) return null;
                            
                            return (
                              <Card key={quote.id} className="p-4 bg-white hover:shadow-md transition-shadow">
                                <div className="flex items-start gap-4">
                                  {/* Trust Score */}
                                  <div className="flex-shrink-0">
                                    <TrustScoreGauge score={displayAircraft.operator?.trustScore || 0} size="sm" />
                                  </div>

                                  {/* Main Content */}
                                  <div className="flex-1 space-y-3">
                                    {/* Header */}
                                    <div className="flex items-start justify-between">
                                      <div>
                                        <div className="flex items-center gap-2 mb-1">
                                          <h4 className="font-semibold">{displayAircraft.operator?.name || 'Unknown'}</h4>
                                          <Badge className={getStatusColor(quote.status)}>
                                            {getStatusLabel(quote.status)}
                                          </Badge>
                                        </div>
                                        <p className="text-sm text-muted-foreground">
                                          {displayAircraft.type} • {displayAircraft.manufacturer} {displayAircraft.model}
                                        </p>
                                        {quote.aircraftPricing && quote.aircraftPricing.length > 1 && (
                                          <p className="text-xs text-muted-foreground mt-1">
                                            +{quote.aircraftPricing.length - 1} more option{quote.aircraftPricing.length > 2 ? 's' : ''}
                                          </p>
                                        )}
                                      </div>
                                      <div className="text-right">
                                        <p className="text-xl font-bold text-[#335cff]">
                                          ${displayPrice.toLocaleString()}
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                          {quote.aircraftPricing && quote.aircraftPricing.length > 1 ? 'From' : 'Total Price'}
                                        </p>
                                      </div>
                                    </div>

                                    {/* Details Grid */}
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                      <div className="flex items-center gap-2">
                                        <Users className="h-4 w-4 text-muted-foreground" />
                                        <div>
                                          <p className="text-xs text-muted-foreground">Capacity</p>
                                          <p className="text-sm font-medium">{displayAircraft.capacity || 0} pax</p>
                                        </div>
                                      </div>

                                      {quote.flightTime && (
                                        <div className="flex items-center gap-2">
                                          <Clock className="h-4 w-4 text-muted-foreground" />
                                          <div>
                                            <p className="text-xs text-muted-foreground">Flight Time</p>
                                            <p className="text-sm font-medium">{quote.flightTime}h</p>
                                          </div>
                                        </div>
                                      )}

                                      <div className="flex items-center gap-2">
                                        <DollarSign className="h-4 w-4 text-muted-foreground" />
                                        <div>
                                          <p className="text-xs text-muted-foreground">Hourly Rate</p>
                                          <p className="text-sm font-medium">
                                            ${(displayAircraft.hourlyRate || 0).toLocaleString()}
                                          </p>
                                        </div>
                                      </div>

                                      <div className="flex items-center gap-2">
                                        <Calendar className="h-4 w-4 text-muted-foreground" />
                                        <div>
                                          <p className="text-xs text-muted-foreground">{quote.timestamp ? 'Received' : 'Created'}</p>
                                          <p className="text-sm font-medium">
                                            {new Date(quote.timestamp || quote.createdAt || Date.now()).toLocaleDateString()}
                                          </p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Notes */}
                                    {quote.notes && (
                                      <p className="text-sm text-muted-foreground italic bg-muted/30 p-2 rounded">
                                        {quote.notes}
                                      </p>
                                    )}

                                    {/* Footer */}
                                    <div className="flex items-center justify-between pt-2 border-t">
                                      <div className="text-xs text-muted-foreground">
                                        {quote.expiresAt && `Expires: ${new Date(quote.expiresAt).toLocaleDateString()}`}
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          onClick={() => onViewQuote(quote)}
                                        >
                                          View Details
                                        </Button>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </Card>
                            );
                          })}
                        </div>
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </Card>
              );
            })}

            {routeGroups.length === 0 && (
              <Card className="p-12 text-center">
                <p className="text-muted-foreground">No quotes found</p>
              </Card>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
