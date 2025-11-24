import { useState } from 'react';
import { Plane, Plus, X, Search, MapPin, Building2 } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { useTailNumbers, useOperators } from '../hooks/useAircraftData';

interface SearchFormProps {
  onSearch: (criteria: SearchCriteria) => void;
}

export interface SearchCriteria {
  searchType: 'tail' | 'airport' | 'operator';
  tailNumbers?: string[];
  departureAirport?: string;
  arrivalAirport?: string;
  operatorIds?: string[];
  operatorNames?: string[];
}

// Mock airports - in a real app, this would also come from an API
const MOCK_AIRPORTS = [
  { code: 'TEB', name: 'Teterboro Airport', city: 'Teterboro, NJ' },
  { code: 'VNY', name: 'Van Nuys Airport', city: 'Van Nuys, CA' },
  { code: 'MIA', name: 'Miami International Airport', city: 'Miami, FL' },
  { code: 'JFK', name: 'John F. Kennedy International', city: 'New York, NY' },
  { code: 'LAX', name: 'Los Angeles International', city: 'Los Angeles, CA' },
  { code: 'ORD', name: "O'Hare International", city: 'Chicago, IL' },
  { code: 'DFW', name: 'Dallas/Fort Worth International', city: 'Dallas, TX' },
  { code: 'LAS', name: 'Harry Reid International', city: 'Las Vegas, NV' },
  { code: 'BOS', name: 'Logan International Airport', city: 'Boston, MA' },
  { code: 'FLL', name: 'Fort Lauderdale-Hollywood', city: 'Fort Lauderdale, FL' },
  { code: 'ATL', name: 'Hartsfield-Jackson Atlanta', city: 'Atlanta, GA' },
  { code: 'SFO', name: 'San Francisco International', city: 'San Francisco, CA' },
];

interface TailNumberInputProps {
  value: string;
  onChange: (value: string) => void;
  onRemove?: () => void;
  showRemove: boolean;
  index: number;
  availableTails: string[];
}

function TailNumberInput({ value, onChange, onRemove, showRemove, index, availableTails }: TailNumberInputProps) {
  const [open, setOpen] = useState(false);
  const [isFocused, setIsFocused] = useState(false);

  const shouldShowAutocomplete = value.length >= 3;
  const canOpenDropdown = open && shouldShowAutocomplete;

  const filteredResults = availableTails
    .filter((tailNumber) => tailNumber.toLowerCase().includes(value.toLowerCase()))
    .slice(0, 50); // Limit to 50 results for performance

  const hasResults = filteredResults.length > 0;

  return (
    <div className="flex items-end gap-3">
      <div className="flex-1 space-y-2">
        {index === 0 && <Label htmlFor={`tail-number-${index}`}>Tail Number</Label>}
        <Popover open={canOpenDropdown} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none z-10" />
              <Input
                id={`tail-number-${index}`}
                placeholder="Enter tail number (e.g., N123AB)..."
                value={value}
                onChange={(e) => {
                  const upperValue = e.target.value.toUpperCase();
                  onChange(upperValue);
                  if (upperValue.length >= 3) {
                    setOpen(true);
                  } else {
                    setOpen(false);
                  }
                }}
                onFocus={() => {
                  setIsFocused(true);
                  if (value.length >= 3) {
                    setOpen(true);
                  }
                }}
                onBlur={() => setIsFocused(false)}
                className="pl-9 pr-4 h-11 font-mono bg-input-background border-0 hover:bg-accent/50 focus:bg-background focus:ring-2 focus:ring-[#335cff]/20 transition-all uppercase"
              />
              {isFocused && value.length > 0 && value.length < 3 && (
                <p className="text-xs text-muted-foreground mt-1.5">
                  Type {3 - value.length} more character{3 - value.length !== 1 ? 's' : ''} for suggestions
                </p>
              )}
            </div>
          </PopoverTrigger>
          <PopoverContent
            className="p-1 w-[var(--radix-popover-trigger-width)] border-[#335cff]/20 shadow-lg"
            align="start"
            sideOffset={4}
          >
            <div className="max-h-[240px] overflow-y-auto">
              {hasResults ? (
                <div className="space-y-0.5">
                  {filteredResults.map((tailNumber) => (
                    <button
                      key={tailNumber}
                      type="button"
                      onClick={() => {
                        onChange(tailNumber);
                        setOpen(false);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-accent rounded-md transition-colors text-left group"
                    >
                      <Plane className="h-4 w-4 text-muted-foreground group-hover:text-[#335cff] transition-colors flex-shrink-0" />
                      <span className="font-mono group-hover:text-[#335cff] transition-colors">
                        {tailNumber}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                  No tail numbers found matching "{value}"
                </div>
              )}
            </div>
            {hasResults && (
              <div className="px-3 py-2 border-t border-border/50 mt-1">
                <p className="text-xs text-muted-foreground">
                  {filteredResults.length} result{filteredResults.length !== 1 ? 's' : ''} shown
                </p>
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>
      {showRemove && onRemove && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onRemove}
          className="h-11 w-11 hover:bg-destructive/10 hover:text-destructive flex-shrink-0"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

interface OperatorSearchInputProps {
  value: string;
  onChange: (value: string) => void;
  operators: Array<{ id: string; name: string; locations: string[] }>;
  onSelectOperator: (operatorId: string, operatorName: string) => void;
  selectedOperators: string[];
}

function OperatorSearchInput({
  value,
  onChange,
  operators,
  onSelectOperator,
  selectedOperators,
}: OperatorSearchInputProps) {
  const [open, setOpen] = useState(false);

  const shouldShowAutocomplete = value.length >= 2;
  const canOpenDropdown = open && shouldShowAutocomplete;

  const filteredResults = operators
    .filter((operator) =>
      operator.name.toLowerCase().includes(value.toLowerCase()) ||
      operator.locations.some(loc => loc.toLowerCase().includes(value.toLowerCase()))
    )
    .slice(0, 50);

  const hasResults = filteredResults.length > 0;

  return (
    <div className="space-y-2">
      <Label>Search Operators ({operators.length} available)</Label>
      <Popover open={canOpenDropdown} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <div className="relative">
            <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none z-10" />
            <Input
              placeholder="Search by operator name or location..."
              value={value}
              onChange={(e) => {
                onChange(e.target.value);
                if (e.target.value.length >= 2) {
                  setOpen(true);
                } else {
                  setOpen(false);
                }
              }}
              onFocus={() => {
                if (value.length >= 2) {
                  setOpen(true);
                }
              }}
              className="pl-9 pr-4 h-11 bg-input-background border-0 hover:bg-accent/50 focus:bg-background focus:ring-2 focus:ring-[#335cff]/20 transition-all"
            />
          </div>
        </PopoverTrigger>
        <PopoverContent
          className="p-1 w-[var(--radix-popover-trigger-width)] border-[#335cff]/20 shadow-lg"
          align="start"
          sideOffset={4}
        >
          <div className="max-h-[320px] overflow-y-auto">
            {hasResults ? (
              <div className="space-y-0.5">
                {filteredResults.map((operator) => {
                  const isSelected = selectedOperators.includes(operator.id);

                  return (
                    <button
                      key={operator.id}
                      type="button"
                      onClick={() => {
                        onSelectOperator(operator.id, operator.name);
                        setOpen(false);
                      }}
                      className={`w-full flex items-start gap-3 px-3 py-3 hover:bg-accent rounded-md transition-colors text-left ${
                        isSelected ? 'bg-blue-50' : ''
                      }`}
                    >
                      <Building2 className={`h-4 w-4 mt-0.5 flex-shrink-0 ${
                        isSelected ? 'text-[#335cff]' : 'text-muted-foreground'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className={`font-medium ${isSelected ? 'text-[#335cff]' : ''}`}>
                          {operator.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {operator.locations.slice(0, 3).join(', ')}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                No operators found matching "{value}"
              </div>
            )}
          </div>
          {hasResults && (
            <div className="px-3 py-2 border-t border-border/50 mt-1">
              <p className="text-xs text-muted-foreground">
                {filteredResults.length} result{filteredResults.length !== 1 ? 's' : ''} shown
              </p>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

interface AirportInputProps {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder: string;
}

function AirportInput({ value, onChange, label, placeholder }: AirportInputProps) {
  const [open, setOpen] = useState(false);
  const [isFocused, setIsFocused] = useState(false);

  const shouldShowAutocomplete = value.length >= 2;
  const canOpenDropdown = open && shouldShowAutocomplete;

  const filteredResults = MOCK_AIRPORTS.filter((airport) =>
    airport.code.toLowerCase().includes(value.toLowerCase()) ||
    airport.name.toLowerCase().includes(value.toLowerCase()) ||
    airport.city.toLowerCase().includes(value.toLowerCase())
  );

  const hasResults = filteredResults.length > 0;

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Popover open={canOpenDropdown} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <div className="relative">
            <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none z-10" />
            <Input
              placeholder={placeholder}
              value={value}
              onChange={(e) => {
                const upperValue = e.target.value.toUpperCase();
                onChange(upperValue);
                if (upperValue.length >= 2) {
                  setOpen(true);
                } else {
                  setOpen(false);
                }
              }}
              onFocus={() => {
                setIsFocused(true);
                if (value.length >= 2) {
                  setOpen(true);
                }
              }}
              onBlur={() => setIsFocused(false)}
              className="pl-9 pr-4 h-11 bg-input-background border-0 hover:bg-accent/50 focus:bg-background focus:ring-2 focus:ring-[#335cff]/20 transition-all uppercase"
            />
            {isFocused && value.length > 0 && value.length < 2 && (
              <p className="text-xs text-muted-foreground mt-1.5">
                Type {2 - value.length} more character{2 - value.length !== 1 ? 's' : ''} for suggestions
              </p>
            )}
          </div>
        </PopoverTrigger>
        <PopoverContent
          className="p-1 w-[var(--radix-popover-trigger-width)] border-[#335cff]/20 shadow-lg"
          align="start"
          sideOffset={4}
        >
          <div className="max-h-[280px] overflow-y-auto">
            {hasResults ? (
              <div className="space-y-0.5">
                {filteredResults.map((airport) => (
                  <button
                    key={airport.code}
                    type="button"
                    onClick={() => {
                      onChange(`${airport.code} - ${airport.name}`);
                      setOpen(false);
                    }}
                    className="w-full flex items-start gap-3 px-3 py-2.5 hover:bg-accent rounded-md transition-colors text-left group"
                  >
                    <MapPin className="h-4 w-4 text-muted-foreground group-hover:text-[#335cff] transition-colors flex-shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono group-hover:text-[#335cff] transition-colors">
                          {airport.code}
                        </span>
                        <span className="text-sm text-muted-foreground truncate">
                          {airport.name}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">{airport.city}</p>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                No airports found matching "{value}"
              </div>
            )}
          </div>
          {hasResults && (
            <div className="px-3 py-2 border-t border-border/50 mt-1">
              <p className="text-xs text-muted-foreground">
                {filteredResults.length} result{filteredResults.length !== 1 ? 's' : ''} found
              </p>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function SearchFormIntegrated({ onSearch }: SearchFormProps) {
  const [activeTab, setActiveTab] = useState<'tail' | 'airport' | 'operator'>('tail');

  // Load real data
  const { tailNumbers: tailNumbersData, loading: tailsLoading } = useTailNumbers();
  const { operators: operatorsData, loading: operatorsLoading } = useOperators();

  // Tail search state
  const [tailNumbers, setTailNumbers] = useState<string[]>(['']);
  const [bulkInput, setBulkInput] = useState('');

  // Airport search state
  const [departureAirport, setDepartureAirport] = useState('');
  const [arrivalAirport, setArrivalAirport] = useState('');

  // Operator search state
  const [selectedOperators, setSelectedOperators] = useState<string[]>([]);
  const [selectedOperatorNames, setSelectedOperatorNames] = useState<string[]>([]);
  const [operatorSearchQuery, setOperatorSearchQuery] = useState('');

  // Extract just the tail numbers for autocomplete
  const availableTailNumbers = tailNumbersData.map(t => t.tailNumber);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (activeTab === 'tail') {
      const validTailNumbers = tailNumbers.filter((tn) => tn.trim() !== '');
      if (validTailNumbers.length > 0) {
        onSearch({
          searchType: 'tail',
          tailNumbers: validTailNumbers
        });
      }
    } else if (activeTab === 'airport') {
      if (departureAirport || arrivalAirport) {
        onSearch({
          searchType: 'airport',
          departureAirport,
          arrivalAirport
        });
      }
    } else if (activeTab === 'operator') {
      if (selectedOperators.length > 0) {
        onSearch({
          searchType: 'operator',
          operatorIds: selectedOperators,
          operatorNames: selectedOperatorNames
        });
      }
    }
  };

  const handleBulkSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const parsed = bulkInput
      .split(/[,\s]+/)
      .map(tn => tn.trim().toUpperCase())
      .filter(tn => tn.length > 0);

    if (parsed.length > 0) {
      onSearch({
        searchType: 'tail',
        tailNumbers: parsed
      });
    }
  };

  const handleAddTailNumber = () => {
    setTailNumbers([...tailNumbers, '']);
  };

  const handleRemoveTailNumber = (index: number) => {
    setTailNumbers(tailNumbers.filter((_, i) => i !== index));
  };

  const handleChangeTailNumber = (index: number, value: string) => {
    const newTailNumbers = [...tailNumbers];
    newTailNumbers[index] = value;
    setTailNumbers(newTailNumbers);
  };

  const handleSelectOperator = (operatorId: string, operatorName: string) => {
    if (selectedOperators.includes(operatorId)) {
      setSelectedOperators(selectedOperators.filter(id => id !== operatorId));
      setSelectedOperatorNames(selectedOperatorNames.filter(name => name !== operatorName));
    } else {
      setSelectedOperators([...selectedOperators, operatorId]);
      setSelectedOperatorNames([...selectedOperatorNames, operatorName]);
    }
  };

  const singleValidCount = tailNumbers.filter((tn) => tn.trim() !== '').length;
  const bulkValidCount = bulkInput.split(/[,\s]+/).filter(tn => tn.trim().length > 0).length;

  return (
    <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="w-full">
      <TabsList className="mb-6 grid w-full grid-cols-3">
        <TabsTrigger value="tail" className="gap-2">
          <Plane className="h-4 w-4" />
          Tail Number
        </TabsTrigger>
        <TabsTrigger value="airport" className="gap-2">
          <MapPin className="h-4 w-4" />
          Airport
        </TabsTrigger>
        <TabsTrigger value="operator" className="gap-2">
          <Building2 className="h-4 w-4" />
          Operator
        </TabsTrigger>
      </TabsList>

      {/* Tail Number Search */}
      <TabsContent value="tail" className="mt-0">
        {tailsLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            Loading tail numbers from database...
          </div>
        ) : (
          <Tabs defaultValue="single" className="w-full">
            <TabsList className="mb-6">
              <TabsTrigger value="single">Single</TabsTrigger>
              <TabsTrigger value="bulk">Bulk</TabsTrigger>
            </TabsList>

            {/* Single Mode */}
            <TabsContent value="single" className="mt-0">
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-3">
                  {tailNumbers.map((tailNumber, index) => (
                    <TailNumberInput
                      key={index}
                      value={tailNumber}
                      onChange={(value) => handleChangeTailNumber(index, value)}
                      onRemove={() => handleRemoveTailNumber(index)}
                      showRemove={tailNumbers.length > 1}
                      index={index}
                      availableTails={availableTailNumbers}
                    />
                  ))}
                </div>

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAddTailNumber}
                  className="w-full h-11 border-2 border-dashed border-muted hover:border-[#335cff] hover:bg-blue-50 hover:text-[#335cff] transition-all"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Another Tail Number
                </Button>

                <Button
                  type="submit"
                  className="w-full h-12 bg-[#335cff] hover:bg-[#2847cc] shadow-md"
                  disabled={singleValidCount === 0}
                >
                  <Search className="h-5 w-5 mr-2" />
                  Search {singleValidCount > 0 ? `${singleValidCount} ` : ''}Aircraft
                </Button>
              </form>
            </TabsContent>

            {/* Bulk Mode */}
            <TabsContent value="bulk" className="mt-0">
              <form onSubmit={handleBulkSubmit} className="space-y-5">
                <div className="space-y-2">
                  <Label htmlFor="bulk-input">Tail Numbers</Label>
                  <Textarea
                    id="bulk-input"
                    placeholder="Enter tail numbers separated by commas or spaces&#10;&#10;Example:&#10;N123AB, N456CD, N789EF"
                    value={bulkInput}
                    onChange={(e) => setBulkInput(e.target.value.toUpperCase())}
                    className="min-h-[160px] font-mono bg-input-background border-0 hover:bg-accent/50 focus:bg-background focus:ring-2 focus:ring-[#335cff]/20 transition-all resize-none"
                  />
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      Separate tail numbers with commas or spaces
                    </p>
                    {bulkInput.trim() && (
                      <p className="text-sm font-medium text-[#335cff]">
                        {bulkValidCount} tail number{bulkValidCount !== 1 ? 's' : ''} detected
                      </p>
                    )}
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full h-12 bg-[#335cff] hover:bg-[#2847cc] shadow-md"
                  disabled={bulkValidCount === 0}
                >
                  <Search className="h-5 w-5 mr-2" />
                  Search {bulkValidCount > 0 ? `${bulkValidCount} ` : ''}Aircraft
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        )}
      </TabsContent>

      {/* Airport Search */}
      <TabsContent value="airport" className="mt-0">
        <form onSubmit={handleSubmit} className="space-y-5">
          <AirportInput
            value={departureAirport}
            onChange={setDepartureAirport}
            label="Departure Airport"
            placeholder="Enter airport code or name..."
          />

          <AirportInput
            value={arrivalAirport}
            onChange={setArrivalAirport}
            label="Arrival Airport"
            placeholder="Enter airport code or name..."
          />

          <div className="pt-1">
            <p className="text-sm text-muted-foreground">
              Search by departure, arrival, or both airports to find available aircraft
            </p>
          </div>

          <Button
            type="submit"
            className="w-full h-12 bg-[#335cff] hover:bg-[#2847cc] shadow-md"
            disabled={!departureAirport && !arrivalAirport}
          >
            <Search className="h-5 w-5 mr-2" />
            Search Aircraft by Route
          </Button>
        </form>
      </TabsContent>

      {/* Operator Search */}
      <TabsContent value="operator" className="mt-0">
        {operatorsLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            Loading operators from database...
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <OperatorSearchInput
              value={operatorSearchQuery}
              onChange={setOperatorSearchQuery}
              operators={operatorsData}
              onSelectOperator={handleSelectOperator}
              selectedOperators={selectedOperators}
            />

            {selectedOperatorNames.length > 0 && (
              <div className="space-y-2">
                <Label>Selected Operators</Label>
                <div className="flex flex-wrap gap-2">
                  {selectedOperatorNames.map((name, idx) => (
                    <div key={idx} className="flex items-center gap-1 bg-blue-50 text-[#335cff] px-3 py-1 rounded-md text-sm">
                      <span>{name}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedOperators(selectedOperators.filter((_, i) => i !== idx));
                          setSelectedOperatorNames(selectedOperatorNames.filter((_, i) => i !== idx));
                        }}
                        className="hover:bg-blue-100 rounded p-0.5"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <p className="text-sm text-muted-foreground">
                {selectedOperators.length} operator{selectedOperators.length !== 1 ? 's' : ''} selected
              </p>
              {selectedOperators.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedOperators([]);
                    setSelectedOperatorNames([]);
                  }}
                >
                  Clear Selection
                </Button>
              )}
            </div>

            <Button
              type="submit"
              className="w-full h-12 bg-[#335cff] hover:bg-[#2847cc] shadow-md"
              disabled={selectedOperators.length === 0}
            >
              <Search className="h-5 w-5 mr-2" />
              Search {selectedOperators.length > 0 ? `${selectedOperators.length} ` : ''}Operator Fleet{selectedOperators.length !== 1 ? 's' : ''}
            </Button>
          </form>
        )}
      </TabsContent>
    </Tabs>
  );
}
