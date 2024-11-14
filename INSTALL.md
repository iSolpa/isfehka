# Panama Electronic Invoicing - HKA Integration
## Installation and Setup Guide

### Prerequisites

1. Odoo Installation:
   - Odoo version 17.0 or 18.0
   - Python 3.8 or higher
   - PostgreSQL 12 or higher

2. HKA Credentials:
   - Token Empresa
   - Token Password
   - Access to HKA's WSDL URL
   - Test environment credentials (for development)

3. System Requirements:
   - Linux/Unix system recommended
   - Minimum 4GB RAM
   - 2 CPU cores
   - 20GB disk space

### Installation Steps

1. Install Required Python Package:

bash
pip3 install zeep


2. Module Installation:

   a. Download the module:
   ```bash
   cd /path/to/odoo/addons
   git clone https://github.com/indepsol/isfehka.git
   ```

   b. Update Odoo's module list:
   - Go to Apps menu
   - Click on "Update Apps List" in the top menu
   - Click "Update" in the dialog

   c. Install the module:
   - Search for "Panama Electronic Invoicing"
   - Click Install

### Configuration

1. HKA Credentials Setup:
   - Navigate to Settings → General Settings → Electronic Invoicing
   - Fill in the following fields:
     * HKA Token Empresa
     * HKA Token Password
     * HKA WSDL URL
   - Enable/disable test mode as needed
   - Click Save

2. User Access Rights:
   - Go to Settings → Users & Companies → Users
   - Edit users who need access to electronic invoicing
   - Under "Access Rights" tab, assign one of these groups:
     * Electronic Invoice User: Can create and send invoices
     * Electronic Invoice Manager: Can configure settings and cancel documents

3. Journal Configuration:
   - Go to Accounting → Configuration → Journals
   - Select or create sales journal for electronic invoices
   - Configure the journal code (used as punto de facturación)

4. Tax Configuration:
   - Verify ITBMS tax rates are properly set up (7%, 10%, 15%)
   - Ensure tax mapping matches HKA requirements

### Usage Instructions

1. Partner Setup:
   - Create/edit customer record
   - Fill in RUC and DV fields
   - Click "Verify RUC" to validate with HKA
   - Ensure address and contact information is complete

2. Creating Electronic Invoices:
   - Create new customer invoice
   - Select appropriate document type
   - Fill in required information
   - Post invoice to send to HKA automatically

3. Handling Responses:
   - Check HKA status in invoice form
   - View CUFE and response messages
   - Handle any errors that occur

4. Cancelling Documents:
   - Open posted invoice
   - Click "Cancel in HKA"
   - Provide cancellation reason
   - Confirm cancellation

### Troubleshooting

1. Connection Issues:
   - Verify network connectivity to HKA services
   - Check WSDL URL configuration
   - Validate credentials in settings
   - Review Odoo server logs for errors

2. RUC Verification Problems:
   - Ensure RUC format is correct
   - Verify RUC is active in HKA system
   - Check partner configuration

3. Invoice Submission Errors:
   - Verify all required fields are filled
   - Check tax configuration
   - Validate partner RUC status
   - Review error messages in invoice form

4. Common Error Solutions:
   - "Invalid credentials": Verify tokens in settings
   - "Connection timeout": Check network and HKA service status
   - "Invalid RUC": Verify partner configuration
   - "Document already exists": Check for duplicate invoices

### Security Considerations

1. Credential Management:
   - Store tokens securely
   - Regularly rotate passwords
   - Limit access to configuration settings

2. Data Protection:
   - Regular database backups
   - Secure network configuration
   - SSL/TLS for all connections

3. User Access:
   - Regular audit of user permissions
   - Remove access for inactive users
   - Monitor system logs

### Support and Updates

1. Technical Support:
   - Email: support@indepsol.net
   - Website: https://www.indepsol.net
   - Support hours: Monday-Friday, 8:00 AM - 5:00 PM (Panama Time)

2. Updates and Maintenance:
   - Regular module updates for bug fixes
   - Compatibility updates for Odoo versions
   - Feature enhancements based on feedback

3. Documentation:
   - Online documentation: https://docs.indepsol.net/isfehka
   - Release notes: https://github.com/indepsol/isfehka/releases
   - API documentation available upon request

### Support and Updates

1. Technical Support:
   - Email: soporte@isolpa.com
   - Website: https://isolpa.com
   - Support hours: Monday-Friday, 8:00 AM - 5:00 PM (Panama Time)

2. Updates and Maintenance:
   - Regular module updates for bug fixes
   - Compatibility updates for Odoo versions
   - Feature enhancements based on feedback

3. Documentation:
   - Online documentation: https://
   - Release notes: https://github.com/isolpa/isfehka/releases
   - API documentation available upon request

### Version Information

- Module Version: 1.0.0
- Supported Odoo Versions: 17.0, 18.0
- Last Updated: November 2024
- License: Odoo Proprietary License (OPL-1)

### Legal Compliance

- No warranties or guarantees are provided by Independent Solutions.

For additional support or custom development needs, please contact Independent Solutions.