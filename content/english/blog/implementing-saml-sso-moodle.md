---
title: "Implementing SAML/SSO Authentication in Moodle"
date: "2024-05-07T10:00:00+08:00"
image: "images/blog/blog-post-5.jpg"
author: "Alex Chen"
type: "post"
categories: ["Security", "Infrastructure & Cloud"]
tags: ["SAML 2.0", "Moodle", "SSO", "Azure AD", "auth_saml2"]
description: "Technical walkthrough of integrating SAML 2.0 SSO into Moodle using the auth_saml2 plugin. Covers certificate management, IdP metadata XML debugging, and Azure AD attribute mapping for production deployments."
---

Password fatigue in higher education is a massive security liability. When Global Tech University was managing active directory credentials, LMS passwords, and separate portal logins, our helpdesk was spending 40% of its time on password resets. Students would reuse weak passwords, leading to compromised accounts and academic integrity issues. The clear solution was to centralize authentication using Single Sign-On (SSO) backed by SAML 2.0.

While Moodle has built-in LDAP and OAuth2 plugins, configuring it to act as a strict SAML Service Provider (SP) against a modern Identity Provider (IdP) like Azure AD or Okta requires navigating the notoriously complex `auth_saml2` plugin. This post details our architectural approach, the critical configuration pitfalls, and how to debug SAML assertions when things inevitably go wrong.


## The SAML 2.0 Flow Explained

Before diving into configuration, it is vital to understand what actually happens when a student clicks "Login" via SAML.

1. **The SP-Initiated Login**: The student arrives at Moodle (the Service Provider) and clicks the SSO button.
2. **The AuthnRequest**: Moodle generates a base64-encoded XML document called an `AuthnRequest` and redirects the student's browser to the Identity Provider (IdP).
3. **Authentication**: The student logs into the IdP (e.g., Azure AD), potentially completing Multi-Factor Authentication (MFA).
4. **The SAML Assertion**: The IdP redirects the user back to Moodle's Assertion Consumer Service (ACS) URL, carrying a signed XML `Assertion`.
5. **Validation & Session**: Moodle validates the XML signature, extracts the user's attributes (like email or student ID), matches them to a local Moodle user, and initiates a PHP session.

## Configuring the auth_saml2 Plugin

Moodle's `auth_saml2` plugin (often the one developed by Catalyst IT) is the de-facto standard. However, the UI configuration can be brittle. I strongly prefer defining the core SAML parameters in Moodle's `config.php` to prevent accidental UI changes and to keep infrastructure as code.

Here is how we lock down the SAML configuration directly in `config.php`:

```php
// Prevent UI modification of core SAML settings
$CFG->forced_plugin_settings = [
    'auth_saml2' => [
        'idpmetadata' => 'https://login.microsoftonline.com/our-tenant-id/federationmetadata/2007-06/federationmetadata.xml?appid=our-app-id',
        'spmetadata' => 'https://moodle.globaltech.edu/auth/saml2/sp/metadata.php',
        'mapping_moodle_username' => 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
        'mapping_moodle_email' => 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
        'mapping_moodle_firstname' => 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
        'mapping_moodle_lastname' => 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
        'autocreate' => 1, // Automatically provision new users on first login
        'updateuser' => 1, // Update fields on every login
    ]
];
```

### The NameID vs. Claim Attribute Dilemma

The most common reason a SAML integration fails is attribute mapping mismatch. Moodle needs a unique identifier to map the incoming IdP user to a local `mdl_user` record.

Historically, SAML relies on the `NameID` field in the Subject of the assertion. However, modern IdPs (especially Azure AD) often send a persistent, opaque string as the `NameID` and include the actual usable username (like `jdoe@globaltech.edu`) in an Attribute claim.

You must explicitly tell Moodle which XML attribute claim contains the username. As shown in the config above, we map `mapping_moodle_username` to the Azure AD UPN claim schema. If you get this wrong, Moodle will either fail to log the user in or, worse, create duplicate accounts.

## Certificates and Key Rotation

SAML security relies entirely on PKI (Public Key Infrastructure). Moodle must sign its `AuthnRequest` (if configured to do so), and it must validate the signature on the IdP's `Assertion`.

By default, the `auth_saml2` plugin generates a self-signed certificate for the Service Provider. **Do not use this default certificate in production.**

Generate a robust X.509 certificate and private key specifically for SAML signing (this is separate from your web server's TLS certificate).

```bash
openssl req -x509 -sha256 -nodes -days 3650 -newkey rsa:2048 -keyout moodle_saml.key -out moodle_saml.crt
```

Place these files in Moodle's `moodledata/saml2` directory and ensure the permissions are restricted so the web server user can read them, but nothing else can.

## Debugging: The SAML Tracer

When a user attempts to log in and sees a generic "Authentication Failed" error, Moodle's PHP error logs often don't provide the full picture. The issue is usually within the encrypted or base64-encoded XML payload.

To debug this, you need a browser extension like **SAML Tracer** (available for Firefox and Chrome). 

Here is what a successful IdP Assertion looks like when decoded. Pay close attention to the `<saml:AttributeStatement>`:

```xml
<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_123456789" IssueInstant="2024-05-07T10:05:00Z" Version="2.0">
  <saml:Issuer>https://sts.windows.net/our-tenant-id/</saml:Issuer>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <!-- Signature details omitted -->
  </ds:Signature>
  <saml:Subject>
    <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">ABC123XYZ</saml:NameID>
    <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData InResponseTo="ONELOGIN_987654321" NotOnOrAfter="2024-05-07T10:10:00Z" Recipient="https://moodle.globaltech.edu/auth/saml2/sp/saml2-acs.php/moodle.globaltech.edu"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:AttributeStatement>
    <saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name">
      <saml:AttributeValue>jdoe@globaltech.edu</saml:AttributeValue>
    </saml:Attribute>
    <saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname">
      <saml:AttributeValue>John</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
```

If Moodle fails to log the user in, use SAML Tracer to capture this XML. Verify that:
1. The `Recipient` exactly matches your ACS URL.
2. The `NotOnOrAfter` timestamp hasn't expired (check your server's NTP synchronization!).
3. The `Attribute Name` exactly matches the mappings in your Moodle configuration.

Implementing SAML correctly is a tedious exercise in XML namespace alignment. But once it is working, the reduction in support tickets and the increase in security posture make it one of the highest ROI infrastructure upgrades an educational institution can perform.


