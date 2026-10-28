import hashlib
import json
import re
import uuid
from urllib.parse import quote, urlencode
from xml.etree import ElementTree as ET
from django.core.cache import cache
from .security import ERPError, credentials, request

DOCTYPES = {"suppliers": "Supplier", "purchase_orders": "Purchase Order", "receipts": "Purchase Receipt", "invoices": "Purchase Invoice", "payments": "Payment Entry"}
ZOHO = {"suppliers": ("contacts", "contacts", "contact", "contact_id"), "purchase_orders": ("purchaseorders", "purchaseorders", "purchaseorder", "purchaseorder_id"), "invoices": ("bills", "bills", "bill", "bill_id"), "payments": ("vendorpayments", "vendorpayments", "vendorpayment", "payment_id")}
REGIONS = {"in", "com", "eu", "com.au", "jp", "ca", "com.cn", "sa"}
VOUCHERS = {"purchase_orders": "Purchase Order", "receipts": "Receipt Note", "invoices": "Purchase", "payments": "Payment"}


def safe_xml(data):
    try:
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-16-le" if data.startswith(b"<\x00") else "utf-16-be" if data.startswith(b"\x00<") else "utf-8-sig"
        text = data.decode(encoding)
    except UnicodeError:
        raise ERPError("ERP returned unsupported XML encoding.") from None
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ERPError("ERP XML contains unsupported entity declarations.")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise ERPError("Tally returned invalid XML.") from None


def xml_dict(element):
    result = dict(element.attrib)
    for child in element:
        value = xml_dict(child) if len(child) else (child.text or "")
        if child.tag in result:
            if not isinstance(result[child.tag], list): result[child.tag] = [result[child.tag]]
            result[child.tag].append(value)
        else: result[child.tag] = value
    return result


class Adapter:
    def __init__(self, connection):
        self.connection = connection
        self.config = connection.config
        self.secret = credentials(connection)
        self.base = self.config.get("base_url", "").rstrip("/")

    def json(self, path, method="GET", payload=None):
        headers = {"Accept": "application/json", "Content-Type": "application/json", **self.headers()}
        return request(self.base + path, method, headers, json.dumps(payload).encode() if payload is not None else None)


class ERPNext(Adapter):
    def headers(self):
        return {"Authorization": f"token {self.secret['api_key']}:{self.secret['api_secret']}"}

    def test(self):
        self.json("/api/resource/Company/" + quote(self.config["company"], safe=""))
        return "ERPNext credentials and company access verified."

    def pull(self, resource, page):
        filters = [["company", "=", self.config["company"]]] if resource != "suppliers" else []
        result = self.json("/api/resource/" + quote(DOCTYPES[resource], safe="") + "?" + urlencode({"limit_page_length": 50, "limit_start": (page-1)*50, "fields": '["name"]', "filters": json.dumps(filters), "order_by": "name asc"}))
        records = result.get("data", [])
        return [(str(row["name"]), self.json("/api/resource/" + quote(DOCTYPES[resource], safe="") + "/" + quote(row["name"], safe="")).get("data", {})) for row in records], len(records) == 50

    def send(self, resource, payload):
        payload = dict(payload)
        payload["doctype"] = DOCTYPES[resource]
        if resource != "suppliers":
            payload["company"] = self.config["company"]
            payload["docstatus"] = 0
        result = self.json("/api/resource/" + quote(DOCTYPES[resource], safe=""), "POST", payload)
        external_id = (result.get("data") or {}).get("name")
        if not external_id: raise ERPError("ERPNext did not return a document ID. Reconcile the outcome before retrying.")
        return str(external_id)


class ZohoBooks(Adapter):
    resources = ZOHO
    def __init__(self, connection):
        super().__init__(connection)
        self.region = self.config["region"]
        self.base = f"https://www.zohoapis.{self.region}/books/v3"

    def headers(self):
        key = f"erp-token:{self.connection.id}:{self.connection.updated_at.timestamp()}"
        token = cache.get(key)
        if not token:
            result = request(f"https://accounts.zoho.{self.region}/oauth/v2/token", "POST", {"Content-Type": "application/x-www-form-urlencoded"}, urlencode({"grant_type": "refresh_token", "client_id": self.config["client_id"], "client_secret": self.secret["client_secret"], "refresh_token": self.secret["refresh_token"]}).encode())
            token = result.get("access_token")
            if not token: raise ERPError("Zoho authorization failed. Check the data centre, OAuth scopes and refresh token.")
            cache.set(key, token, max(1, min(int(result.get("expires_in", 3600))-120, 3480)))
        return {"Authorization": "Zoho-oauthtoken " + token}

    def api(self, path, method="GET", payload=None, params=None):
        query = {"organization_id": self.config["organization_id"], **(params or {})}
        result = self.json(path + "?" + urlencode(query), method, payload)
        if result.get("code", 0) != 0: raise ERPError("Zoho rejected the request. Check permissions, mappings and organization settings.")
        return result

    def test(self):
        self.api("/organizations/" + quote(self.config["organization_id"], safe=""))
        return "Zoho Books organization access verified."

    def pull(self, resource, page):
        if resource not in self.resources: raise ERPError("This resource is not supported by the selected Zoho product.")
        path, plural, singular, id_key = self.resources[resource]
        params = {"page": page, "per_page": 50}
        if resource == "suppliers": params["contact_type"] = "vendor"
        result = self.api("/" + path, params=params)
        records = []
        for row in result.get(plural, []):
            external_id = str(row[id_key])
            detail = self.api("/" + path + "/" + quote(external_id, safe=""))
            records.append((external_id, detail.get(singular, row)))
        return records, bool(result.get("page_context", {}).get("has_more_page"))

    def send(self, resource, payload):
        if resource not in self.resources: raise ERPError("This Zoho connection does not support this resource.")
        path, _, singular, id_key = self.resources[resource]
        result = self.api("/" + path, "POST", payload)
        external_id = (result.get(singular) or {}).get(id_key)
        if not external_id: raise ERPError("Zoho did not return the record ID. Reconcile the outcome before retrying.")
        return str(external_id)


class ZohoInventory(ZohoBooks):
    resources = {"suppliers": ZOHO["suppliers"], "purchase_orders": ZOHO["purchase_orders"], "receipts": ("purchasereceives", "purchasereceives", "purchase_receive", "receive_id")}

    def __init__(self, connection):
        super().__init__(connection)
        self.base = f"https://www.zohoapis.{self.region}/inventory/v1"

    def test(self):
        result = self.api("/organizations")
        if not any(str(row.get("organization_id")) == self.config["organization_id"] for row in result.get("organizations", [])):
            raise ERPError("The configured organization is not accessible with these Inventory OAuth permissions.")
        return "Zoho Inventory organization access verified."

    def send(self, resource, payload):
        if resource != "receipts": raise ERPError("Use the Zoho Books connector for supplier and purchase-order writes.")
        payload = dict(payload)
        purchase_order_id = payload.pop("purchaseorder_id", None)
        if not purchase_order_id: raise ERPError("An Inventory purchase order ID is required for the receipt.")
        result = self.api("/purchasereceives", "POST", payload, {"purchaseorder_id": purchase_order_id})
        receive_id = result.get("purchase_receive", {}).get("receive_id")
        if not receive_id: raise ERPError("Inventory did not return a receipt ID. Reconcile before retrying.")
        return str(receive_id)


class DynamicsFinance(Adapter):
    def headers(self):
        key = f"erp-token:{self.connection.id}:{self.connection.updated_at.timestamp()}"
        token = cache.get(key)
        if not token:
            result = request(f"https://login.microsoftonline.com/{quote(self.config['entra_tenant_id'], safe='')}/oauth2/v2.0/token", "POST", {"Content-Type": "application/x-www-form-urlencoded"}, urlencode({"grant_type": "client_credentials", "client_id": self.config["client_id"], "client_secret": self.secret["client_secret"], "scope": self.base+"/.default"}).encode())
            token = result.get("access_token")
            if not token: raise ERPError("Microsoft Entra authorization failed. Check the application and Finance service-user permissions.")
            cache.set(key, token, max(1, min(int(result.get("expires_in", 3600))-120, 3480)))
        return {"Authorization": "Bearer " + token}

    def entity(self, resource):
        entity = self.config.get("entities", {}).get(resource)
        if not isinstance(entity, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(entity.get("collection", ""))) or not entity.get("key_fields"):
            raise ERPError("Configure this Finance entity collection and key fields using your environment metadata.")
        return entity

    def test(self):
        metadata = request(self.base+"/data/$metadata", headers=self.headers(), xml=True)
        root = safe_xml(metadata)
        names = {node.attrib.get("Name") for node in root.iter() if node.tag.endswith("EntitySet")}
        if not names: raise ERPError("Finance returned no OData entity sets.")
        for resource in self.config.get("entities", {}):
            if self.entity(resource)["collection"] not in names:
                raise ERPError(f"Configured Finance entity for {resource} is not exposed in this environment.")
        for mapping in self.config.get("document_maps", {}).values():
            for field in ("header_collection", "line_collection"):
                if mapping.get(field) and mapping[field] not in names:
                    raise ERPError("A configured Finance write collection is not exposed in this environment.")
        return "Finance OAuth and OData metadata access verified. Legal-entity and field mappings still require review."

    def pull(self, resource, page):
        entity = self.entity(resource)
        company = self.config["legal_entity"].replace("'", "''")
        query = {"cross-company": "true", "$filter": f"dataAreaId eq '{company}'", "$top": 50, "$skip": (page-1)*50, "$orderby": ",".join(entity["key_fields"])}
        result = self.json("/data/"+entity["collection"]+"?"+urlencode(query))
        rows = result.get("value", [])
        records = []
        for row in rows:
            if str(row.get("dataAreaId", "")).casefold() != self.config["legal_entity"].casefold():
                raise ERPError("Finance returned a record outside the configured legal entity. Sync was stopped.")
            values = [row.get(field) for field in entity["key_fields"]]
            if any(value is None or value == "" for value in values):
                raise ERPError("A Finance record is missing its configured key fields.")
            records.append((hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(), row))
        return records, bool(result.get("@odata.nextLink")) or len(rows) == 50

    def send(self, resource, payload):
        if payload.get("operations"):
            operations = payload["operations"]
            reference = str(payload.get("external_reference", ""))
            if not reference or len(reference) > 200: raise ERPError("Map a stable Finance external reference before sending.")
            if not isinstance(operations, list) or not 1 <= len(operations) <= 500:
                raise ERPError("Finance batch must contain 1 to 500 operations.")
            batch, changeset = "batch_"+uuid.uuid4().hex, "changeset_"+uuid.uuid4().hex
            parts = [f"--{batch}\r\nContent-Type: multipart/mixed; boundary={changeset}\r\n\r\n"]
            for index, operation in enumerate(operations, 1):
                collection = operation.get("collection", "")
                body = dict(operation.get("body", {}))
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", collection): raise ERPError("Invalid Finance collection name.")
                body["dataAreaId"] = self.config["legal_entity"]
                parts.append(f"--{changeset}\r\nContent-Type: application/http\r\nContent-Transfer-Encoding: binary\r\nContent-ID: {index}\r\n\r\nPOST {self.base}/data/{collection} HTTP/1.1\r\nContent-Type: application/json\r\n\r\n"+json.dumps(body)+"\r\n")
            parts.append(f"--{changeset}--\r\n--{batch}--\r\n")
            response = request(self.base+"/data/$batch", "POST", {**self.headers(), "Content-Type": "multipart/mixed; boundary="+batch}, "".join(parts).encode(), xml=True)
            statuses = re.findall(rb"HTTP/1\.[01]\s+(\d{3})", response)
            if len(statuses) != len(operations) or any(not 200 <= int(status) < 300 for status in statuses):
                raise ERPError("Finance did not confirm every batch operation. Inspect the ERP and reconcile before retrying.")
            return reference
        entity = self.entity(resource)
        payload = dict(payload)
        payload["dataAreaId"] = self.config["legal_entity"]
        # Invoice lines are a separate Finance entity and cannot be omitted.
        # Use an atomic OData changeset supplied by an environment-specific
        # extension for compound records; this generic transport only writes
        # a single entity and must not create an invoice header by itself.
        if resource in {"invoices", "purchase_orders", "receipts"}:
            raise ERPError("Finance document headers and lines need an environment-specific atomic mapping. Export the reviewed package for your Finance implementation partner.")
        result = self.json("/data/"+entity["collection"], "POST", payload)
        values = [result.get(field) for field in entity["key_fields"]]
        if any(value in (None, "") for value in values): raise ERPError("Finance did not return the configured record keys. Reconcile the outcome before retrying.")
        if resource == "suppliers" and result.get("VendorAccountNumber"): return str(result["VendorAccountNumber"])
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


class Tally(Adapter):
    def collection(self, kind, resource=None):
        root = ET.Element("ENVELOPE")
        header = ET.SubElement(root, "HEADER")
        for key, value in {"VERSION": "1", "TALLYREQUEST": "Export", "TYPE": "Collection", "ID": "KriyoPayCollection"}.items(): ET.SubElement(header, key).text = value
        desc = ET.SubElement(ET.SubElement(root, "BODY"), "DESC")
        variables = ET.SubElement(desc, "STATICVARIABLES")
        ET.SubElement(variables, "SVCURRENTCOMPANY").text = self.config["company"]
        ET.SubElement(variables, "SVEXPORTFORMAT").text = "$$SysName:XML"
        message = ET.SubElement(ET.SubElement(desc, "TDL"), "TDLMESSAGE")
        collection = ET.SubElement(message, "COLLECTION", {"NAME": "KriyoPayCollection", "ISMODIFY": "No"})
        ET.SubElement(collection, "TYPE").text = kind
        ET.SubElement(collection, "NATIVEMETHOD").text = "*"
        if resource in VOUCHERS:
            ET.SubElement(collection, "FILTER").text = "KriyoPayVoucherType"
            formula = ET.SubElement(message, "SYSTEM", {"TYPE": "Formulae", "NAME": "KriyoPayVoucherType"})
            formula.text = '$VoucherTypeName = "' + VOUCHERS[resource] + '"'
        result = safe_xml(request(self.base, "POST", {"Content-Type": "text/xml; charset=utf-8"}, ET.tostring(root, encoding="utf-8"), xml=True))
        if result.find(".//LINEERROR") is not None: raise ERPError("Tally rejected the collection. Check the company name and gateway configuration.")
        return result

    def test(self):
        result = self.collection("Company")
        if self.config["company"] not in {node.attrib.get("NAME", "") for node in result.iter("COMPANY")}:
            raise ERPError("The configured company is not loaded or available in Tally.")
        return "Tally gateway and loaded company verified."

    def pull(self, resource, page):
        root = self.collection("Ledger" if resource == "suppliers" else "Voucher", resource)
        nodes = list(root.iter("LEDGER" if resource == "suppliers" else "VOUCHER"))
        if resource == "suppliers":
            # Other creditor subgroups can be configured explicitly.
            parents = set(self.config.get("supplier_groups", ["Sundry Creditors"]))
            nodes = [node for node in nodes if node.findtext("PARENT") in parents]
        records = []
        for node in nodes[(page-1)*50:page*50]:
            key = node.findtext("GUID") or node.attrib.get("REMOTEID") or node.findtext("MASTERID") or node.attrib.get("NAME")
            if not key: raise ERPError("Tally returned a record without a stable identifier.")
            records.append((str(key), xml_dict(node)))
        return records, len(nodes) > page*50

    def send(self, resource, payload):
        if resource not in {"suppliers", "invoices", "payments"}:
            raise ERPError("Tally purchase orders and goods receipts require inventory-specific voucher mappings. Use the review package.")
        # The service prepares the exact XML with a stable record GUID/REMOTEID.
        raw = payload.get("xml")
        if not isinstance(raw, str): raise ERPError("A reviewed Tally XML document is required.")
        result = safe_xml(request(self.base, "POST", {"Content-Type": "text/xml; charset=utf-8"}, raw.encode(), xml=True))
        errors = result.findtext(".//ERRORS")
        created = result.findtext(".//CREATED")
        if result.find(".//LINEERROR") is not None or errors not in {None, "0"} or created != "1":
            raise ERPError("Tally did not confirm exactly one created record. Reconcile its import report before sending again.")
        return str(payload["external_reference"])


def adapter(connection):
    return {"ERPNEXT": ERPNext, "ZOHO_BOOKS": ZohoBooks, "ZOHO_INVENTORY": ZohoInventory, "DYNAMICS_FINANCE": DynamicsFinance, "TALLY": Tally}[connection.provider](connection)
