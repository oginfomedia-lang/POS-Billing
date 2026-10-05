// Root component: loads the counter config, then shows the router.
import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from './app/router';
import { useCounterStore } from './store/counterStore';

export function App() {
  const { config, error, load } = useCounterStore();

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <section className="placeholder-page">
        <h1>Counter setup problem</h1>
        <p>{error}</p>
      </section>
    );
  }
  if (!config) return null;

  return <RouterProvider router={router} />;
}
