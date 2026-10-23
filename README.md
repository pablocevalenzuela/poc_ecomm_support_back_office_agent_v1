# poc_ecomm_support_back_office_agent_v1

This is a proof of concept (PoC) for an e-commerce back-office support agent designed to perform the following tasks:

1. Receive low-stock alerts from the Shopify store.
2. Check the stock level of a specific product via chat.
3. Check the status of and manage orders from the Shopify online store via chat.
4. Request new stock from suppliers via chat.
5. Essentially, the seller can manage an e-commerce business from a single interface—the chat—without needing to open countless Excel spreadsheets or separate ERP, CRM, or other applications.


## Set up and Run
```bash
git clone https://github.com/pablocevalenzuela/poc_ecomm_support_back_office_agent_v1.git # Clone the repository.
source venv/bin/activate          # Activate virtual environment ./venv (Python 3.14)
pip install -r requirements.txt # Install dependences.
make dev                          # URL is http://localhost:8000  (UI at /ui)
```

## URLs
1. Main: http://localhost:8000/
2. API (endpoints): http://localhost:8000/api/
3. Chat/UI: http://localhost:8000/ui


## Tech-stack
* [JavaScript](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
* [React](https://reactjs.org/)


## How to use
The salesperson opens the chat and begins providing back-office support to the online store's customers.


## Colaboration
Contributions are welcome.
