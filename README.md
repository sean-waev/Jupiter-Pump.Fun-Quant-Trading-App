# Jupiter-Pump.Fun-Quant-Trading-Application

![Solana Logo](https://solana.com/src/img/branding/solanaLogoMark.svg)

## Overview

This application is a quantitative trading system built for the Solana blockchain, combining Python for data processing and trading logic with NestJS for API services. The system consists of multiple interconnected modules that communicate via a multiprocessing queue.

## Features

- Real-time price data collection from Jupiter
- Queue-based inter-process communication
- Advanced trading strategies ("Infinite Money Glitch")
- REST API interface via NestJS
- Multi-process architecture for performance

## Prerequisites

- Python 3.9+
- Node.js 16+
- npm/yarn
- Solana CLI tools
- Redis (for queue management)

## Installation

### Python Dependencies

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/MacOS
# or
.\venv\Scripts\activate   # Windows
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

Python dependencies should include (but not limited to):
- solana-py
- numpy
- pandas
- multiprocess
- redis
- websockets
- aiohttp

### NestJS Dependencies

1. Navigate to the NestJS directory:

```bash
cd nestjs-app
```

2. Install Node.js dependencies:

```bash
npm install
# or
yarn install
```

NestJS dependencies should include:
- @nestjs/common
- @nestjs/core
- @nestjs/platform-express
- rxjs
- reflect-metadata
- solana-web3.js

## Running the Application

The application requires 5 separate terminal windows to run all components:

### Terminal 1: Queue Manager
```bash
python3 queueManager.py
```

### Terminal 2: Fun Pump
```bash
python3 funPump.py
```

### Terminal 3: Jupiter Prices
```bash
python3 jupitersPrices.py
```

### Terminal 4: Trading Strategy
```bash
python3 infiniteMoneyGlitch.py
```

### Terminal 5: NestJS API
```bash
cd nestjs-app
npm run start
```

## Application Architecture

```
+----------------+       +----------------+       +-----------------+
|  jupitersPrices|------>|  queueManager  |<------|    funPump      |
+----------------+       +----------------+       +-----------------+
                                    |
                                    v
+-----------------+       +------------------+
| infiniteMoney   |<------|   NestJS API     |
| Glitch          |       | (npm run start)  |
+-----------------+       +------------------+
```

## Configuration

Before running, create a `.env` file in the root directory with the following variables:

```ini
SOLANA_RPC_ENDPOINT=https://api.mainnet-beta.solana.com
JUPITER_API_ENDPOINT=https://quote-api.jup.ag
REDIS_HOST=localhost
REDIS_PORT=6379
TRADING_STRATEGY=mean_reversion
RISK_FACTOR=0.02
```

## API Endpoints

The NestJS application provides the following endpoints:

- `GET /api/prices` - Get current price data
- `POST /api/orders` - Submit a new order
- `GET /api/positions` - Get current positions
- `GET /api/performance` - Get strategy performance metrics

## Monitoring

Access the dashboard at `http://localhost:3000` after starting the NestJS application.

## Troubleshooting

1. **Queue not initializing**: Ensure `queueManager.py` is started first
2. **Connection issues**: Verify Solana RPC endpoint is accessible
3. **Dependency errors**: Check all packages are installed with correct versions

## License

MIT License

## Support

For issues or questions, please open an issue in the repository.
