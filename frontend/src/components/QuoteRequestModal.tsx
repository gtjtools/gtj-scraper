import { useState } from 'react';
import { Aircraft } from '../lib/mock-data';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Separator } from './ui/separator';
import { CheckCircle2 } from 'lucide-react';

interface QuoteRequestModalProps {
  aircraft: Aircraft | null;
  isOpen: boolean;
  onClose: () => void;
  searchCriteria?: any;
}

export function QuoteRequestModal({ aircraft, isOpen, onClose, searchCriteria }: QuoteRequestModalProps) {
  const [submitted, setSubmitted] = useState(false);
  const [formData, setFormData] = useState({
    clientName: '',
    clientEmail: '',
    clientPhone: '',
    specialRequests: ''
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => {
      setSubmitted(false);
      onClose();
      setFormData({
        clientName: '',
        clientEmail: '',
        clientPhone: '',
        specialRequests: ''
      });
    }, 2000);
  };

  if (!aircraft) return null;

  if (submitted) {
    return (
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader className="sr-only">
            <DialogTitle>Quote Request Sent</DialogTitle>
            <DialogDescription>
              Your quote request has been sent to {aircraft.operator.name}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <CheckCircle2 className="h-16 w-16 text-green-500 mb-4" />
            <h3 className="text-xl font-semibold mb-2">Quote Request Sent!</h3>
            <p className="text-muted-foreground">
              {aircraft.operator.name} will respond within 2 hours
            </p>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Request Quote from Operator</DialogTitle>
          <DialogDescription>
            Request pricing from {aircraft.operator.name} for {aircraft.manufacturer} {aircraft.model}
          </DialogDescription>
        </DialogHeader>

        <div className="bg-gray-50 rounded-lg p-4 space-y-2">
          <h4 className="font-semibold">Trip Summary</h4>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Route</p>
              <p className="font-medium">{searchCriteria?.departure || 'N/A'} → {searchCriteria?.arrival || 'N/A'}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Departure</p>
              <p className="font-medium">{searchCriteria?.departureDate || 'N/A'}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Passengers</p>
              <p className="font-medium">{searchCriteria?.passengers || 0}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Aircraft</p>
              <p className="font-medium">{aircraft.tailNumber}</p>
            </div>
          </div>
        </div>

        <Separator />

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="clientName">Client Name *</Label>
            <Input
              id="clientName"
              value={formData.clientName}
              onChange={(e) => setFormData({ ...formData, clientName: e.target.value })}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="clientEmail">Client Email *</Label>
            <Input
              id="clientEmail"
              type="email"
              value={formData.clientEmail}
              onChange={(e) => setFormData({ ...formData, clientEmail: e.target.value })}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="clientPhone">Client Phone *</Label>
            <Input
              id="clientPhone"
              type="tel"
              value={formData.clientPhone}
              onChange={(e) => setFormData({ ...formData, clientPhone: e.target.value })}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="specialRequests">Special Requests (Optional)</Label>
            <Textarea
              id="specialRequests"
              value={formData.specialRequests}
              onChange={(e) => setFormData({ ...formData, specialRequests: e.target.value })}
              placeholder="Catering, ground transportation, pets, special equipment, etc."
              rows={4}
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" className="bg-[#335cff] hover:bg-[#2847cc]">
              Submit Request
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
