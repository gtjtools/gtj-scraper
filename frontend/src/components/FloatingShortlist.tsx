import { ShoppingCart, FileText } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { motion, AnimatePresence } from 'motion/react';

interface FloatingShortlistProps {
  count: number;
  onViewShortlist: () => void;
  onGenerateQuote: () => void;
}

export function FloatingShortlist({ count, onViewShortlist, onGenerateQuote }: FloatingShortlistProps) {
  if (count === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 100, opacity: 0 }}
        className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50"
      >
        <div className="bg-white rounded-full shadow-2xl border-2 border-[#335cff] px-6 py-4 flex items-center gap-4">
          <button
            onClick={onViewShortlist}
            className="flex items-center gap-3 hover:opacity-80 transition-opacity"
          >
            <div className="relative">
              <ShoppingCart className="h-6 w-6 text-[#335cff]" />
              <Badge 
                className="absolute -top-2 -right-2 h-5 w-5 flex items-center justify-center p-0 bg-[#335cff] hover:bg-[#335cff]"
              >
                {count}
              </Badge>
            </div>
            <div className="text-left">
              <p className="font-semibold text-sm">Shortlist</p>
              <p className="text-xs text-muted-foreground">
                {count} {count === 1 ? 'aircraft' : 'aircraft'}
              </p>
            </div>
          </button>

          <div className="h-10 w-px bg-gray-200" />

          <Button
            onClick={onGenerateQuote}
            className="bg-[#335cff] hover:bg-[#2847cc] shadow-lg"
            size="lg"
          >
            <FileText className="h-5 w-5 mr-2" />
            Generate Quote
          </Button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}