// Message bref et discret (région aria-live), disparaît seul.
import { useCallback, useEffect, useRef, useState } from "react";

export function useNotice(delai = 3600) {
  const [message, setMessage] = useState("");
  const t = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notifier = useCallback((m: string) => {
    setMessage(m);
    if (t.current) clearTimeout(t.current);
    t.current = setTimeout(() => setMessage(""), delai);
  }, [delai]);
  useEffect(() => () => { if (t.current) clearTimeout(t.current); }, []);
  return { message, notifier };
}
