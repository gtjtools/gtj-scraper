import { useState, useEffect } from 'react';
import { LogoFull } from './components/LogoFull';
import { Navigation } from './components/Navigation';
import { SearchFormIntegrated as SearchForm, SearchCriteria } from './components/SearchFormIntegrated';
import { QuoteRequestModal } from './components/QuoteRequestModal';
import { AircraftDetailsModal } from './components/AircraftDetailsModal';
import { ClientInboxList } from './components/ClientInboxList';
import { ClientQuotesModal } from './components/ClientQuotesModal';
import { CurrentQuotes } from './components/CurrentQuotes';
import { ActivityFeed } from './components/ActivityFeed';
import { ClientsPage } from './components/ClientsPage';
import { FinancialsPage } from './components/FinancialsPage';
import { QuotesPage } from './components/QuotesPage';
import { FlightsPage } from './components/FlightsPage';
import { TrackedFlightsPage } from './components/TrackedFlightsPage';
import { OperatorsPage } from './components/OperatorsPage';
import { NotificationsSidebar } from './components/NotificationsSidebar';
import { ShortlistSheet } from './components/ShortlistSheet';
import { FloatingShortlist } from './components/FloatingShortlist';
import { CreateQuotePage, QuoteFormData } from './components/CreateQuotePage';
import { QuotePreviewPage } from './components/QuotePreviewPage';
import { CheckoutPage } from './components/CheckoutPage';
import { mockAircraft, mockQuotes, mockActivities, mockClients, mockBrokerPerformance, mockTrackedFlights, mockNotifications, Aircraft, Quote, Client, TrackedFlight, Notification } from './lib/mock-data';
import { Inbox, FileText, Activity, Bell, LogOut } from 'lucide-react';
import { Badge } from './components/ui/badge';
import { Card } from './components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Toaster, toast } from 'sonner';
import { searchByTailNumber, searchCharterOperators, searchAircraftByOperator } from './services/api';
import { convertTailSearchToAircraft, convertCharterOperatorToAircraft } from './services/dataAdapter';

interface DashboardProps {
  onLogout?: () => void;
}

export default function Dashboard({ onLogout }: DashboardProps) {
  const [currentPage, setCurrentPage] = useState('inbox');
  const [searchResults, setSearchResults] = useState<Aircraft[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [selectedAircraft, setSelectedAircraft] = useState<Aircraft | null>(null);
  const [showQuoteModal, setShowQuoteModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [searchCriteria, setSearchCriteria] = useState<SearchCriteria | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>(mockQuotes);
  const [activities] = useState(mockActivities);
  const [clients, setClients] = useState(mockClients);
  const [brokerPerformance] = useState(mockBrokerPerformance);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [selectedClientQuotes, setSelectedClientQuotes] = useState<Quote[]>([]);
  const [showClientQuotesModal, setShowClientQuotesModal] = useState(false);
  const [shortlistedAircraft, setShortlistedAircraft] = useState<Aircraft[]>([
    mockAircraft[1], // Bombardier Challenger 350
    mockAircraft[2], // Gulfstream G280
    mockAircraft[4]  // Embraer Phenom 300
  ]);
  const [showShortlistSheet, setShowShortlistSheet] = useState(false);
  const [trackedFlights, setTrackedFlights] = useState<TrackedFlight[]>(mockTrackedFlights);
  const [notifications, setNotifications] = useState<Notification[]>(mockNotifications);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifiedTripScores] = useState<Set<string>>(new Set());
  const [notifiedAOGs] = useState<Set<string>>(new Set());

  // Handle browser back/forward buttons - keep navigation within the app
  useEffect(() => {
    // Push initial state
    window.history.pushState({ page: currentPage }, '', window.location.href);

    const handlePopState = (event: PopStateEvent) => {
      // Handle internal navigation
      if (event.state && event.state.page) {
        setCurrentPage(event.state.page);
      } else {
        setCurrentPage('inbox');
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Update browser history when page changes
  useEffect(() => {
    window.history.pushState({ page: currentPage }, '', window.location.href);
  }, [currentPage]);

  // Check for notifications on tracked flights
  useEffect(() => {
    const newNotifications: Notification[] = [];
    
    trackedFlights.forEach(flight => {
      // Notify on new AOG
      if (flight.hasAOG && flight.aogReportId && !notifiedAOGs.has(flight.id)) {
        newNotifications.push({
          id: `aog-${flight.id}-${Date.now()}`,
          type: 'aog-incident',
          title: `AOG Incident: ${flight.aircraft.tailNumber}`,
          description: `${flight.bookingReference} - Aircraft is under maintenance at ${flight.currentLocation}`,
          timestamp: new Date().toISOString(),
          isRead: false,
          actionUrl: 'track',
          metadata: {
            flightId: flight.id,
            tailNumber: flight.aircraft.tailNumber,
            bookingReference: flight.bookingReference
          }
        });
        notifiedAOGs.add(flight.id);
      }

      // Notify on first TripScore
      if (flight.tripScore?.isFirstScore && !notifiedTripScores.has(flight.id)) {
        newNotifications.push({
          id: `tripscore-${flight.id}-${Date.now()}`,
          type: 'tripscore-generated',
          title: `TripScore Generated: ${flight.aircraft.tailNumber}`,
          description: `${flight.bookingReference} - TripScore: ${flight.tripScore.score}/100`,
          timestamp: new Date().toISOString(),
          isRead: false,
          actionUrl: 'track',
          metadata: {
            flightId: flight.id,
            tailNumber: flight.aircraft.tailNumber,
            bookingReference: flight.bookingReference,
            tripScore: flight.tripScore.score
          }
        });
        notifiedTripScores.add(flight.id);
      }

      // Notify on low TripScore (< 70)
      if (flight.tripScore && flight.tripScore.score < 70 && !flight.tripScore.isFirstScore && !notifiedTripScores.has(`${flight.id}-low`)) {
        newNotifications.push({
          id: `tripscore-low-${flight.id}-${Date.now()}`,
          type: 'tripscore-low',
          title: `Low TripScore Alert: ${flight.aircraft.tailNumber}`,
          description: `${flight.bookingReference} - TripScore dropped to ${flight.tripScore.score}/100`,
          timestamp: new Date().toISOString(),
          isRead: false,
          actionUrl: 'track',
          metadata: {
            flightId: flight.id,
            tailNumber: flight.aircraft.tailNumber,
            bookingReference: flight.bookingReference,
            tripScore: flight.tripScore.score
          }
        });
        notifiedTripScores.add(`${flight.id}-low`);
      }
    });

    if (newNotifications.length > 0) {
      setNotifications(prev => [...newNotifications, ...prev]);
    }
  }, [trackedFlights, notifiedTripScores, notifiedAOGs]);
  
  // Quote preview and checkout states
  const [quotePreviewData, setQuotePreviewData] = useState<QuoteFormData | null>(null);
  const [checkoutData, setCheckoutData] = useState<{
    aircraft: Aircraft;
    pricing: { operatorPrice: number; myPrice: number };
    tripDetails: {
      departure: string;
      arrival: string;
      date: string;
      passengers: number;
      clientName: string;
    };
  } | null>(null);

  const handleSearch = async (criteria: SearchCriteria) => {
    setSearchCriteria(criteria);
    setHasSearched(true);
    setCurrentPage('flights');
    window.scrollTo({ top: 0, behavior: 'smooth' });

    try {
      if (criteria.searchType === 'tail' && criteria.tailNumbers) {
        // Search by tail numbers
        toast.info(`Searching for ${criteria.tailNumbers.length} aircraft...`);

        // Fetch real data from API for each tail number
        const searchPromises = criteria.tailNumbers.map(tailNumber =>
          searchByTailNumber(tailNumber).catch(err => {
            console.error(`Error searching for ${tailNumber}:`, err);
            return { found: false, tail_number: tailNumber };
          })
        );

        const searchResults = await Promise.all(searchPromises);

        // Convert API results to Aircraft objects
        let allAircraft: Aircraft[] = [];
        searchResults.forEach(result => {
          try {
            const aircraft = convertTailSearchToAircraft(result);
            allAircraft = [...allAircraft, ...aircraft];
          } catch (conversionError) {
            console.error('Error converting search result:', conversionError, result);
          }
        });

        if (allAircraft.length === 0) {
          toast.warning(`No aircraft found for the specified tail numbers.`);
          setSearchResults([]);
        } else {
          toast.success(`Found ${allAircraft.length} aircraft!`);
          setSearchResults(allAircraft);
        }
      } else if (criteria.searchType === 'operator' && criteria.operatorNames) {
        // Search by operators - get their actual fleet from FAA database
        toast.info(`Searching fleet for ${criteria.operatorNames.length} operator(s)...`);

        // Search FAA Part 135 database for each operator's aircraft
        const allAircraft: Aircraft[] = [];

        for (const operatorName of criteria.operatorNames) {
          try {
            // Search Part 135 data for this operator's aircraft
            const operatorAircraft = await searchAircraftByOperator(operatorName);

            // Get charter operator enrichment data
            const charterResults = await searchCharterOperators();
            const charterOperator = charterResults.data.find(op =>
              op.company.toLowerCase().includes(operatorName.toLowerCase()) ||
              operatorName.toLowerCase().includes(op.company.toLowerCase())
            );

            // Convert each aircraft to our format
            operatorAircraft.forEach((faaRecord, index) => {
              try {
                // Build a tail search result format for the converter
                const searchResult = {
                  found: true,
                  tail_number: String(faaRecord['Registration Number']),
                  operators: charterOperator ? [{
                    operator_name: faaRecord['Part 135 Certificate Holder Name'],
                    certificate_designator: faaRecord['Certificate Designator'],
                    charter_data: charterOperator.data,
                    score: charterOperator.score || 0
                  }] : [{
                    operator_name: faaRecord['Part 135 Certificate Holder Name'],
                    certificate_designator: faaRecord['Certificate Designator'],
                    charter_data: null,
                    score: 0
                  }],
                  aircraft: [{
                    registration: String(faaRecord['Registration Number']),
                    serial_number: faaRecord['Serial Number'],
                    make_model: faaRecord['Aircraft Make/Model/Series'],
                    operator: faaRecord['Part 135 Certificate Holder Name'],
                    certificate_designator: faaRecord['Certificate Designator'],
                    faa_district: faaRecord['FAA Certificate Holding District Office']
                  }]
                };

                const converted = convertTailSearchToAircraft(searchResult);
                allAircraft.push(...converted);
              } catch (conversionError) {
                console.error('Error converting operator aircraft:', conversionError, faaRecord);
              }
            });
          } catch (error) {
            console.error(`Error searching for operator ${operatorName}:`, error);
          }
        }

        if (allAircraft.length > 0) {
          toast.success(`Found ${allAircraft.length} aircraft from ${criteria.operatorNames.length} operator(s)!`);
          setSearchResults(allAircraft);
        } else {
          toast.warning(`No aircraft found for the selected operator(s).`);
          setSearchResults([]);
        }
      } else if (criteria.searchType === 'airport') {
        // Search by airport
        toast.info('Searching aircraft by airport...');

        // Use the airport code/name to search Part 135 data
        const airportQuery = criteria.airport || '';
        const charterResults = await searchCharterOperators(airportQuery);

        if (charterResults.data.length > 0) {
          const aircraft = convertCharterOperatorToAircraft(charterResults.data);
          if (aircraft.length > 0) {
            toast.success(`Found ${aircraft.length} aircraft at or near ${airportQuery}!`);
            setSearchResults(aircraft);
          } else {
            toast.warning(`No detailed aircraft information available for ${airportQuery}.`);
            setSearchResults([]);
          }
        } else {
          toast.warning(`No aircraft found near ${airportQuery}.`);
          setSearchResults([]);
        }
      }
    } catch (error: any) {
      console.error('Search error:', error);
      toast.error(`Search error: ${error.message || 'Please try again'}`);
      setSearchResults([]);
    }
  };

  const handleRequestQuote = (aircraft: Aircraft) => {
    setSelectedAircraft(aircraft);
    setShowQuoteModal(true);
  };

  const handleViewDetails = (aircraft: Aircraft) => {
    setSelectedAircraft(aircraft);
    setShowDetailsModal(true);
  };

  const handleViewQuote = (quote: Quote) => {
    // For legacy quotes with single aircraft
    if (quote.aircraft) {
      setSelectedAircraft(quote.aircraft);
      setShowDetailsModal(true);
    } else if (quote.aircraftOptions && quote.aircraftOptions.length > 0) {
      setSelectedAircraft(quote.aircraftOptions[0]);
      setShowDetailsModal(true);
    }
  };

  const handleAcceptQuote = (quote: Quote) => {
    setQuotes(quotes.map(q => 
      q.id === quote.id ? { ...q, status: 'accepted' as const } : q
    ));
    toast.success('Quote accepted!');
  };

  const handleDeclineQuote = (quote: Quote) => {
    setQuotes(quotes.map(q => 
      q.id === quote.id ? { ...q, status: 'declined' as const } : q
    ));
    toast.success('Quote declined');
  };

  const handleSelectClient = (client: Client, clientQuotes: Quote[]) => {
    setSelectedClient(client);
    setSelectedClientQuotes(clientQuotes);
    setShowClientQuotesModal(true);
  };

  const handleNavigate = (page: string) => {
    if (page === 'new-flight') {
      setCurrentPage('inbox');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      setCurrentPage(page);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleAddToShortlist = (aircraft: Aircraft) => {
    if (!shortlistedAircraft.find(a => a.id === aircraft.id)) {
      setShortlistedAircraft([...shortlistedAircraft, aircraft]);
      toast.success(`${aircraft.manufacturer} ${aircraft.model} added to shortlist`);
    }
  };

  const handleRemoveFromShortlist = (aircraftId: string) => {
    setShortlistedAircraft(shortlistedAircraft.filter(a => a.id !== aircraftId));
    toast.success('Removed from shortlist');
  };

  const handleGenerateQuote = () => {
    if (shortlistedAircraft.length === 0) return;
    
    // Close shortlist sheet and navigate to create quote page
    setShowShortlistSheet(false);
    setCurrentPage('create-quote');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSaveDraft = (quoteData: QuoteFormData) => {
    // Create new quote with status 'draft'
    const newQuote: Quote = {
      id: `q${quotes.length + 1}`,
      client: quoteData.client,
      aircraftOptions: quoteData.aircraftPricing.map(p => p.aircraft),
      aircraftPricing: quoteData.aircraftPricing,
      aircraft: quoteData.aircraftPricing[0]?.aircraft, // Legacy compatibility
      route: {
        departure: quoteData.tripType === 'multi-leg' 
          ? (quoteData.legs?.[0]?.departure || 'TBD') 
          : (quoteData.departure || 'TBD'),
        arrival: quoteData.tripType === 'multi-leg' 
          ? (quoteData.legs?.[quoteData.legs.length - 1]?.arrival || 'TBD') 
          : (quoteData.arrival || 'TBD')
      },
      date: quoteData.tripType === 'multi-leg' 
        ? (quoteData.legs?.[0]?.date || new Date().toISOString()) 
        : (quoteData.departureDate || new Date().toISOString()),
      passengers: quoteData.tripType === 'multi-leg' 
        ? (quoteData.legs?.[0]?.passengers || 6) 
        : (quoteData.passengers || 6),
      tripType: quoteData.tripType,
      returnDate: quoteData.returnDate,
      legs: quoteData.legs,
      status: 'draft',
      createdAt: new Date().toISOString(),
      expiresAt: quoteData.expiresAt || new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      title: quoteData.title || `${quoteData.client.name} Flight Quote`,
      message: quoteData.message
    };

    setQuotes([...quotes, newQuote]);
    setShortlistedAircraft([]);
    toast.success('Quote saved as draft!');
    setCurrentPage('quotes');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePreviewQuote = (quoteData: QuoteFormData) => {
    // Save quote data for preview
    setQuotePreviewData(quoteData);
    setCurrentPage('quote-preview');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSendQuote = () => {
    if (!quotePreviewData) return;

    // Create and send quote
    const newQuote: Quote = {
      id: `q${quotes.length + 1}`,
      client: quotePreviewData.client,
      aircraftOptions: quotePreviewData.aircraftPricing.map(p => p.aircraft),
      aircraftPricing: quotePreviewData.aircraftPricing,
      aircraft: quotePreviewData.aircraftPricing[0]?.aircraft,
      route: {
        departure: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[0]?.departure || 'TBD') 
          : (quotePreviewData.departure || 'TBD'),
        arrival: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[quotePreviewData.legs.length - 1]?.arrival || 'TBD') 
          : (quotePreviewData.arrival || 'TBD')
      },
      date: quotePreviewData.tripType === 'multi-leg' 
        ? (quotePreviewData.legs?.[0]?.date || new Date().toISOString()) 
        : (quotePreviewData.departureDate || new Date().toISOString()),
      passengers: quotePreviewData.tripType === 'multi-leg' 
        ? (quotePreviewData.legs?.[0]?.passengers || 6) 
        : (quotePreviewData.passengers || 6),
      tripType: quotePreviewData.tripType,
      returnDate: quotePreviewData.returnDate,
      legs: quotePreviewData.legs,
      status: 'sent',
      createdAt: new Date().toISOString(),
      sentAt: new Date().toISOString(),
      expiresAt: quotePreviewData.expiresAt || new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      title: quotePreviewData.title || `${quotePreviewData.client.name} Flight Quote`,
      message: quotePreviewData.message
    };

    setQuotes([...quotes, newQuote]);
    setShortlistedAircraft([]);
    setQuotePreviewData(null);
    toast.success(`Quote sent to ${quotePreviewData.client.name}!`);
    setCurrentPage('quotes');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleBookFlight = (aircraft: Aircraft, pricing: { operatorPrice: number; myPrice: number }) => {
    if (!quotePreviewData) return;

    setCheckoutData({
      aircraft,
      pricing,
      tripDetails: {
        departure: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[0]?.departure || 'TBD') 
          : (quotePreviewData.departure || 'TBD'),
        arrival: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[quotePreviewData.legs.length - 1]?.arrival || 'TBD') 
          : (quotePreviewData.arrival || 'TBD'),
        date: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[0]?.date || new Date().toISOString()) 
          : (quotePreviewData.departureDate || new Date().toISOString()),
        passengers: quotePreviewData.tripType === 'multi-leg' 
          ? (quotePreviewData.legs?.[0]?.passengers || 0) 
          : (quotePreviewData.passengers || 0),
        clientName: quotePreviewData.client.name
      }
    });
    setCurrentPage('checkout');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCompleteBooking = () => {
    toast.success('Booking confirmed! Confirmation email sent.');
    setCheckoutData(null);
    setQuotePreviewData(null);
    setCurrentPage('inbox');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCancelCreateQuote = () => {
    setCurrentPage('flights');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSaveClient = (clientData: Omit<Client, 'id'>): Client => {
    const newClient: Client = {
      ...clientData,
      id: `c${clients.length + 1}`
    };
    setClients([...clients, newClient]);
    toast.success(`Client "${clientData.name}" saved to database`);
    return newClient;
  };

  const handleViewAOGReport = (flightId: string, aogReportId: string) => {
    toast.info('AOG Report viewer would open here', {
      description: `Viewing report ${aogReportId} for flight ${flightId}`
    });
  };

  const handleFindReplacement = (flight: TrackedFlight) => {
    setSearchCriteria({
      airport: flight.currentLeg.departure,
      date: flight.currentLeg.departureDate,
      passengers: flight.passengers,
      type: 'airport'
    });
    setCurrentPage('flights');
    setHasSearched(true);
    setSearchResults(mockAircraft);
    toast.info('Finding replacement aircraft', {
      description: `Searching for available aircraft at ${flight.currentLeg.departure}`
    });
  };

  const handleMarkNotificationAsRead = (notificationId: string) => {
    setNotifications(prev => 
      prev.map(n => n.id === notificationId ? { ...n, isRead: true } : n)
    );
  };

  const handleMarkAllNotificationsAsRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, isRead: true })));
  };

  const handleNotificationClick = (notification: Notification) => {
    if (notification.actionUrl) {
      setCurrentPage(notification.actionUrl);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const draftQuotesCount = quotes.filter(q => q.status === 'draft').length;
  const newQuotesCount = quotes.filter(q => q.status === 'new').length;
  const inboxQuotes = quotes.filter(q => q.status === 'new' || q.status === 'reviewing');
  const activeQuotes = quotes.filter(q => q.status === 'new' || q.status === 'reviewing');
  const recentQuotes = quotes.filter(q => q.status === 'accepted' || q.status === 'declined');
  const unreadNotificationsCount = notifications.filter(n => !n.isRead).length;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      <Toaster position="top-right" richColors />
      
      {/* Header */}
      <header className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 shadow-lg relative overflow-hidden">
        <div className="absolute inset-0 opacity-20">
          <img
            src="https://images.unsplash.com/photo-1754481387410-7c8c9350372c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w3Nzg4Nzd8MHwxfHNlYXJjaHwxfHxwcml2YXRlJTIwamV0JTIwYWVyaWFsJTIwdmlld3xlbnwxfHx8fDE3NTk5Mjg4NDh8MA&ixlib=rb-4.1.0&q=80&w=1080&utm_source=figma&utm_medium=referral"
            alt=""
            className="w-full h-full object-cover"
          />
        </div>
        <div className="container mx-auto px-6 relative z-10">
          <div className="flex items-center justify-between py-6 border-b border-white/10">
            <LogoFull className="h-[32px] w-auto" />
            <div className="flex items-center gap-4">
              <p className="text-white/90 hidden md:block">Private skies, verified trust.</p>
              <button
                onClick={() => setShowNotifications(true)}
                className="relative p-2 rounded-lg hover:bg-white/10 transition-colors"
              >
                <Bell className="h-5 w-5 text-white" />
                {unreadNotificationsCount > 0 && (
                  <Badge className="absolute -top-1 -right-1 h-5 min-w-5 flex items-center justify-center p-0 bg-red-500 text-white border-2 border-slate-900">
                    {unreadNotificationsCount}
                  </Badge>
                )}
              </button>
              <button
                onClick={onLogout}
                className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-white/10 transition-colors text-white/90 hover:text-white"
                title="Logout"
              >
                <LogOut className="h-5 w-5" />
                <span className="hidden md:inline">Logout</span>
              </button>
            </div>
          </div>
          <div className="py-4">
            <Navigation 
              currentPage={currentPage}
              onNavigate={handleNavigate}
              draftQuotesCount={draftQuotesCount}
              trackedFlightsCount={trackedFlights.length}
            />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Inbox Page */}
        {currentPage === 'inbox' && (
          <>
            {/* Search Section - At the top */}
            <div className="bg-white rounded-2xl shadow-xl p-8 mb-8">
              <div className="mb-6">
                <h1 className="text-3xl font-bold mb-2">Search Aircraft</h1>
                <p className="text-muted-foreground">
                  Search by tail number, airport, or operator to find aircraft and create quotes for your clients
                </p>
              </div>
              <SearchForm onSearch={handleSearch} />
            </div>

            <div className="grid lg:grid-cols-3 gap-8">
          {/* Left Column - Inbox & Quotes */}
          <div className="lg:col-span-2 space-y-6">
            {/* Dashboard Cards */}
            <div className="grid md:grid-cols-3 gap-4">
              <Card className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <Inbox className="h-5 w-5 text-[#335cff]" />
                  {newQuotesCount > 0 && (
                    <Badge variant="default" className="bg-[#335cff]">
                      {newQuotesCount} new
                    </Badge>
                  )}
                </div>
                <p className="text-2xl font-bold">{quotes.length}</p>
                <p className="text-sm text-muted-foreground">Total Quotes</p>
              </Card>

              <Card className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <FileText className="h-5 w-5 text-green-600" />
                </div>
                <p className="text-2xl font-bold">
                  {quotes.filter(q => q.status === 'accepted').length}
                </p>
                <p className="text-sm text-muted-foreground">Accepted</p>
              </Card>

              <Card className="p-6">
                <div className="flex items-center justify-between mb-2">
                  <Activity className="h-5 w-5 text-orange-600" />
                </div>
                <p className="text-2xl font-bold">{activities.length}</p>
                <p className="text-sm text-muted-foreground">Recent Activity</p>
              </Card>
            </div>

            {/* Tabbed Interface for Inbox and Quotes */}
            <Card className="p-6">
              <Tabs defaultValue="inbox">
                <TabsList className="mb-6">
                  <TabsTrigger value="inbox" className="gap-2">
                    <Inbox className="h-4 w-4" />
                    New from Operators
                    {newQuotesCount > 0 && (
                      <Badge variant="secondary" className="ml-1 bg-[#335cff] text-white">
                        {newQuotesCount}
                      </Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="active" className="gap-2">
                    <FileText className="h-4 w-4" />
                    Active
                  </TabsTrigger>
                  <TabsTrigger value="recent" className="gap-2">
                    <FileText className="h-4 w-4" />
                    Recent
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="inbox">
                  <ClientInboxList
                    quotes={inboxQuotes}
                    onSelectClient={handleSelectClient}
                  />
                </TabsContent>

                <TabsContent value="active">
                  <CurrentQuotes 
                    quotes={activeQuotes} 
                    onViewQuote={handleViewQuote}
                  />
                </TabsContent>

                <TabsContent value="recent">
                  <CurrentQuotes 
                    quotes={recentQuotes} 
                    onViewQuote={handleViewQuote}
                  />
                </TabsContent>
              </Tabs>
            </Card>
          </div>

          {/* Right Column - Activity Feed */}
          <div>
            <Card className="p-6 sticky top-6">
              <div className="flex items-center gap-2 mb-6">
                <Activity className="h-5 w-5 text-muted-foreground" />
                <h2 className="font-semibold">Recent Activity</h2>
              </div>
              <ActivityFeed activities={activities} />
            </Card>
          </div>
        </div>
          </>
        )}

        {/* Track Page */}
        {currentPage === 'track' && (
          <TrackedFlightsPage
            trackedFlights={trackedFlights}
            onViewAOGReport={handleViewAOGReport}
            onFindReplacement={handleFindReplacement}
          />
        )}

        {/* Flights Page */}
        {currentPage === 'flights' && hasSearched && (
          <FlightsPage
            searchResults={searchResults}
            searchCriteria={searchCriteria}
            onAddToShortlist={handleAddToShortlist}
            onViewDetails={handleViewDetails}
            shortlistedIds={shortlistedAircraft.map(a => a.id)}
          />
        )}

        {/* Create Quote Page */}
        {currentPage === 'create-quote' && (
          <CreateQuotePage
            shortlistedAircraft={shortlistedAircraft}
            existingClients={clients}
            onSaveDraft={handleSaveDraft}
            onPreviewQuote={handlePreviewQuote}
            onCancel={handleCancelCreateQuote}
            onSaveClient={handleSaveClient}
            onViewAircraftDetails={handleViewDetails}
          />
        )}

        {/* Quote Preview Page */}
        {currentPage === 'quote-preview' && quotePreviewData && (
          <QuotePreviewPage
            quoteData={quotePreviewData}
            onBack={() => setCurrentPage('create-quote')}
            onSend={handleSendQuote}
            onBookFlight={handleBookFlight}
          />
        )}

        {/* Checkout Page */}
        {currentPage === 'checkout' && checkoutData && (
          <CheckoutPage
            aircraft={checkoutData.aircraft}
            pricing={checkoutData.pricing}
            tripDetails={checkoutData.tripDetails}
            onBack={() => setCurrentPage('quote-preview')}
            onComplete={handleCompleteBooking}
          />
        )}

        {/* Quotes Page */}
        {currentPage === 'quotes' && (
          <QuotesPage 
            quotes={quotes} 
            onViewQuote={handleViewQuote}
            onViewDetails={handleViewDetails}
          />
        )}

        {/* Clients Page */}
        {currentPage === 'clients' && (
          <ClientsPage
            clients={clients}
            quotes={quotes}
            onSelectClient={handleSelectClient}
          />
        )}

        {/* Operators Page */}
        {currentPage === 'operators' && (
          <OperatorsPage />
        )}

        {/* Financials Page */}
        {currentPage === 'financials' && (
          <FinancialsPage performance={brokerPerformance} />
        )}
      </main>

      {/* Modals */}
      <QuoteRequestModal
        aircraft={selectedAircraft}
        isOpen={showQuoteModal}
        onClose={() => setShowQuoteModal(false)}
        searchCriteria={searchCriteria}
      />

      <AircraftDetailsModal
        aircraft={selectedAircraft}
        isOpen={showDetailsModal}
        onClose={() => setShowDetailsModal(false)}
        onAddToShortlist={handleAddToShortlist}
        isShortlisted={selectedAircraft ? shortlistedAircraft.some(a => a.id === selectedAircraft.id) : false}
      />

      <ClientQuotesModal
        client={selectedClient}
        quotes={selectedClientQuotes}
        isOpen={showClientQuotesModal}
        onClose={() => setShowClientQuotesModal(false)}
        onViewQuote={handleViewQuote}
        onAcceptQuote={handleAcceptQuote}
        onDeclineQuote={handleDeclineQuote}
      />

      <NotificationsSidebar
        isOpen={showNotifications}
        onClose={() => setShowNotifications(false)}
        notifications={notifications}
        onMarkAsRead={handleMarkNotificationAsRead}
        onMarkAllAsRead={handleMarkAllNotificationsAsRead}
        onNotificationClick={handleNotificationClick}
      />

      <ShortlistSheet
        isOpen={showShortlistSheet}
        onClose={() => setShowShortlistSheet(false)}
        shortlistedAircraft={shortlistedAircraft}
        onRemove={handleRemoveFromShortlist}
        onGenerateQuote={handleGenerateQuote}
        searchCriteria={searchCriteria}
      />

      {/* Floating Shortlist - Hide on create-quote, preview, and checkout pages */}
      {!['create-quote', 'quote-preview', 'checkout'].includes(currentPage) && (
        <FloatingShortlist
          count={shortlistedAircraft.length}
          onViewShortlist={() => setShowShortlistSheet(true)}
          onGenerateQuote={handleGenerateQuote}
        />
      )}
    </div>
  );
}
