import { motion } from "framer-motion";
import {
  useState,
  useRef,
  useEffect,
  useCallback,
  useSyncExternalStore,
  createContext,
  useContext,
} from "react";
import confetti from "canvas-confetti";
import { Check, Star as LucideStar } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { cn } from "../../lib/utils";
import { buttonVariants } from "./button-variants";

// --- MEDIA QUERY HOOK ---

function useMediaQuery(query: string) {
  const subscribe = useCallback((onChange: () => void) => {
    const result = matchMedia(query);
    result.addEventListener("change", onChange);
    return () => result.removeEventListener("change", onChange);
  }, [query]);
  return useSyncExternalStore(subscribe, () => matchMedia(query).matches, () => false);
}

// --- PRICING COMPONENT LOGIC ---

interface PricingPlan {
  name: string;
  price: string;
  yearlyPrice: string;
  period: string;
  features: string[];
  description: string;
  buttonText: string;
  href: string;
  isPopular?: boolean;
}

interface PricingSectionProps {
  plans: PricingPlan[];
  title?: string;
  description?: string;
}

const PricingContext = createContext<{
  isMonthly: boolean;
  setIsMonthly: (value: boolean) => void;
}>({
  isMonthly: true,
  setIsMonthly: () => {},
});

// Main PricingSection Component
export function PricingSection({
  plans,
  title = "Simple, Transparent Pricing",
  description = "Choose the plan that's right for you.",
}: PricingSectionProps) {
  const [isMonthly, setIsMonthly] = useState(true);

  return (
    <PricingContext.Provider value={{ isMonthly, setIsMonthly }}>
      <div className="relative w-full py-20 sm:py-24">
        <div className="relative z-10 max-w-7xl mx-auto px-4 md:px-6">
          <div className="max-w-3xl mx-auto text-center space-y-4 mb-12">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight">
              {title}
            </h2>
            <p className="text-white/40 text-lg whitespace-pre-line">
              {description}
            </p>
          </div>
          <PricingToggle />
          <div className="mt-12 grid grid-cols-1 lg:grid-cols-3 items-start gap-8">
            {plans.map((plan, index) => (
              <PricingCard key={index} plan={plan} index={index} />
            ))}
          </div>
        </div>
      </div>
    </PricingContext.Provider>
  );
}

// Pricing Toggle Component
function PricingToggle() {
  const { isMonthly, setIsMonthly } = useContext(PricingContext);
  const confettiRef = useRef<HTMLDivElement>(null);
  const monthlyBtnRef = useRef<HTMLButtonElement>(null);
  const annualBtnRef = useRef<HTMLButtonElement>(null);

  const [pillStyle, setPillStyle] = useState({});

  useEffect(() => {
    const btnRef = isMonthly ? monthlyBtnRef : annualBtnRef;
    if (btnRef.current) {
      setPillStyle({
        width: btnRef.current.offsetWidth,
        transform: `translateX(${btnRef.current.offsetLeft}px)`,
      });
    }
  }, [isMonthly]);

  const handleToggle = (monthly: boolean) => {
    if (isMonthly === monthly) return;
    setIsMonthly(monthly);

    if (!monthly && confettiRef.current) {
      const rect = annualBtnRef.current?.getBoundingClientRect();
      if (!rect) return;

      const originX = (rect.left + rect.width / 2) / window.innerWidth;
      const originY = (rect.top + rect.height / 2) / window.innerHeight;

      confetti({
        particleCount: 80,
        spread: 80,
        origin: { x: originX, y: originY },
        colors: ["#2563eb", "#3b82f6", "#60a5fa"],
        ticks: 300,
        gravity: 1.2,
        decay: 0.94,
        startVelocity: 30,
      });
    }
  };

  return (
    <div className="flex justify-center">
      <div ref={confettiRef} className="relative flex w-fit items-center rounded-full bg-white/[0.06] border border-white/10 p-1">
        <motion.div
          className="absolute left-0 top-0 h-full rounded-full p-1"
          style={{ ...pillStyle, background: "linear-gradient(135deg, #2563eb, #1d4ed8)" }}
          transition={{ type: "spring", stiffness: 500, damping: 40 }}
        />
        <button
          ref={monthlyBtnRef}
          onClick={() => handleToggle(true)}
          className={cn(
            "relative z-10 rounded-full px-4 sm:px-6 py-2 text-sm font-medium transition-colors",
            isMonthly
              ? "text-white"
              : "text-white/40 hover:text-white/70",
          )}
        >
          Monthly
        </button>
        <button
          ref={annualBtnRef}
          onClick={() => handleToggle(false)}
          className={cn(
            "relative z-10 rounded-full px-4 sm:px-6 py-2 text-sm font-medium transition-colors",
            !isMonthly
              ? "text-white"
              : "text-white/40 hover:text-white/70",
          )}
        >
          Annual
          <span
            className={cn(
              "hidden sm:inline",
              !isMonthly ? "text-white/80" : "",
            )}
          >
            {" "}
            (Save 20%)
          </span>
        </button>
      </div>
    </div>
  );
}

// Pricing Card Component
function PricingCard({ plan, index }: { plan: PricingPlan; index: number }) {
  const { isMonthly } = useContext(PricingContext);
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  return (
    <motion.div
      initial={{ y: 50, opacity: 0 }}
      whileInView={{
        y: plan.isPopular && isDesktop ? -20 : 0,
        opacity: 1,
      }}
      viewport={{ once: true }}
      transition={{
        duration: 0.6,
        type: "spring",
        stiffness: 100,
        damping: 20,
        delay: index * 0.15,
      }}
      className={cn(
        "rounded-2xl p-8 flex flex-col relative",
        plan.isPopular
          ? "border-2 border-accent card-glass shadow-lg shadow-blue-500/5"
          : "card-glass",
      )}
    >
      {plan.isPopular && (
        <div className="absolute top-0 -translate-y-1/2 left-1/2 -translate-x-1/2">
          <div className="py-1.5 px-4 rounded-full flex items-center gap-1.5" style={{ background: "linear-gradient(135deg, #2563eb, #1d4ed8)" }}>
            <LucideStar className="text-white h-4 w-4 fill-current" />
            <span className="text-white text-sm font-semibold">
              Most Popular
            </span>
          </div>
        </div>
      )}
      <div className="flex-1 flex flex-col text-center">
        <h3 className="text-xl font-semibold text-white">{plan.name}</h3>
        <p className="mt-2 text-sm text-white/40">
          {plan.description}
        </p>
        <div className="mt-6 flex items-baseline justify-center gap-x-1">
          <span className="text-5xl font-bold tracking-tight text-white">
            <NumberFlow
              value={
                isMonthly ? Number(plan.price) : Number(plan.yearlyPrice)
              }
              format={{
                style: "currency",
                currency: "JOD",
                minimumFractionDigits: 0,
              }}
              className="font-variant-numeric: tabular-nums"
            />
          </span>
          <span className="text-sm font-semibold leading-6 tracking-wide text-white/40">
            / {plan.period}
          </span>
        </div>
        <p className="text-xs text-white/30 mt-2">
          {isMonthly ? "Billed Monthly" : "Billed Annually"}
        </p>

        <ul
          role="list"
          className="mt-8 space-y-3 text-sm leading-6 text-left text-white/50"
        >
          {plan.features.map((feature) => (
            <li key={feature} className="flex gap-x-3">
              <Check
                className="h-6 w-5 flex-none text-accent-light"
                aria-hidden="true"
              />
              {feature}
            </li>
          ))}
        </ul>

        <div className="mt-auto pt-8">
          <a
            href={plan.href}
            className={cn(
              buttonVariants({
                variant: plan.isPopular ? "default" : "outline",
                size: "lg",
              }),
              "w-full",
            )}
          >
            {plan.buttonText}
          </a>
        </div>
      </div>
    </motion.div>
  );
}
