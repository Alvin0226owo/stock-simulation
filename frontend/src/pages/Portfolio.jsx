import React, { useState, useEffect } from 'react';
import { fetchPortfolio } from '../utils/api';
import PortfolioSummary from '../components/PortfolioSummary';
import PortfolioTable from '../components/PortfolioTable';
import TradeForm from '../components/TradeForm';

function Portfolio() {
  const [initialInvestment] = useState(1000000);
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadPortfolio = async () => {
    setLoading(true);
    try {
      const data = await fetchPortfolio();
      setPortfolio(data);
    } catch (error) {
      console.error('Portfolio error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPortfolio();
  }, []);

  if (loading) return <div className="container mt-5"><div className="alert alert-info">Loading portfolio data...</div></div>;
  if (!portfolio) return <div className="container mt-5"><div className="alert alert-danger">Error loading portfolio data</div></div>;

  return (
    <div className="container mt-5">
      <h2>Portfolio</h2>
      
      <div className="row mb-4">
        <div className="col">
          <PortfolioSummary portfolio={portfolio} initialInvestment={initialInvestment} />
        </div>
      </div>

      <div className="row mb-4">
        <TradeForm onTradeComplete={loadPortfolio} />
      </div>

      <h3>Holdings</h3>
      <PortfolioTable portfolio={portfolio} />

      <button 
        className="btn btn-secondary mt-3" 
        onClick={loadPortfolio}
      >
        Refresh Portfolio
      </button>
    </div>
  );
}

export default Portfolio;