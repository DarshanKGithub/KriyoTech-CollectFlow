"use client";
import { ProcessingStatus } from "@/components/processing-status";

import { useRef, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { Upload } from "lucide-react";

export function InvoiceUploadDialog({open,onClose,onUpload,busy,automatic}: {
  open:boolean;onClose:()=>void;onUpload:(file:File)=>Promise<boolean>;busy:boolean;automatic:boolean;
}) {
  const [file,setFile]=useState<File|null>(null);
  const [error,setError]=useState("");
  const input=useRef<HTMLInputElement>(null);
  function choose(files:FileList|null) {
    setError("");setFile(null);
    if(!files?.length)return;
    if(files.length!==1){setError("Choose one invoice at a time.");return;}
    if(files[0].size>25*1024*1024){setError("Choose a file smaller than 25 MB.");return;}
    if(!/\.(pdf|jpe?g|png|heic|heif)$/i.test(files[0].name)){setError("Choose a PDF, JPG, PNG, HEIC or HEIF invoice.");return;}
    setFile(files[0]);
  }
  function close(){if(busy)return;setFile(null);setError("");onClose();}
  return <Dialog open={open} onClose={close} fullWidth maxWidth="sm" aria-labelledby="invoice-upload-title">
    <Box component="form" onSubmit={async event=>{event.preventDefault();if(!file||busy)return;if(await onUpload(file)){setFile(null);setError("");onClose();}else setError("Upload could not finish. Check the workspace message and retry.");}}>
      <DialogTitle id="invoice-upload-title">Upload an invoice</DialogTitle>
      <DialogContent><DialogContentText sx={{mb:2}}>Choose a supplier invoice to add to your workspace.</DialogContentText>
        <Paper variant="outlined" onDragOver={event=>event.preventDefault()} onDrop={event=>{event.preventDefault();if(!busy)choose(event.dataTransfer.files);}} sx={{p:4,textAlign:"center",borderStyle:"dashed",bgcolor:"action.hover",color:"text.primary",borderColor:"divider"}}>
          <Box sx={{display:"flex",justifyContent:"center",mb:2,color:"primary.main"}}><Upload size={28}/></Box>
          <Button component="label" variant="outlined" disabled={busy}>Choose invoice<input ref={input} hidden type="file" accept="application/pdf,image/jpeg,image/png,image/heic,image/heif" onChange={event=>{choose(event.target.files);event.target.value="";}}/></Button>
          <DialogContentText variant="caption" sx={{mt:2}}>Or drop one file here · PDF, JPG, PNG, HEIC or HEIF · Up to 25 MB</DialogContentText>
        </Paper>
        {busy&&<Box sx={{mt:2}}><ProcessingStatus status="UPLOADING" label="Uploading invoice"/></Box>}
        {file&&<Chip sx={{mt:2,maxWidth:"100%"}} label={`${file.name} · ${(file.size/1024).toFixed(0)} KB`} onDelete={busy?undefined:()=>{setFile(null);if(input.current)input.current.value="";}}/>}
        {error&&<Alert severity="error" sx={{mt:2}}>{error}</Alert>}
        <Alert severity="info" sx={{mt:2}}>{automatic?"Fields will be extracted automatically after upload. Review them before approval.":"Automatic extraction is disabled for this workspace. Review the invoice fields after upload."}</Alert>
      </DialogContent>
      <DialogActions><Button type="button" onClick={close} disabled={busy}>Cancel</Button><Button type="submit" variant="contained" disabled={!file||busy} startIcon={busy?<CircularProgress size={14} color="inherit"/>:<Upload size={15}/>}>{busy?"Uploading…":"Upload invoice"}</Button></DialogActions>
    </Box>
  </Dialog>;
}
