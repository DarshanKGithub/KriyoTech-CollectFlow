"use client";

import Stepper from "@mui/material/Stepper";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";

export function InvoiceProgress({status}: {status: string}) {
  const position = ["UPLOADED","EXTRACTING","EXTRACTION_FAILED"].includes(status) ? 1 : ["REVIEW_REQUIRED","MATCHED","EXCEPTION"].includes(status) ? 2 : ["APPROVAL_PENDING","REJECTED"].includes(status) ? 3 : 4;
  return <Box sx={{my:2}}><Stepper activeStep={position} alternativeLabel sx={{"& .MuiStepLabel-label":{fontSize:11}}}>
    {["Uploaded","Extraction","Review","Approval","Payment"].map((label,index)=><Step key={label}><StepLabel error={(status==="EXTRACTION_FAILED"&&index===1)||(status==="REJECTED"&&index===3)}>{label}</StepLabel></Step>)}
  </Stepper>{status==="EXTRACTION_FAILED"&&<Alert severity="warning" sx={{mt:2}}>Extraction needs a retry or manual field review.</Alert>}</Box>;
}

export function TripProgress({pickup,loaded,delivered}: {pickup:boolean;loaded:boolean;delivered:boolean}) {
  return <Stepper activeStep={delivered?4:loaded?2:pickup?1:0} alternativeLabel sx={{my:2,"& .MuiStepLabel-label":{fontSize:11}}}>
    {["Truck assigned","At pickup","On the way","Delivered"].map(label=><Step key={label}><StepLabel>{label}</StepLabel></Step>)}
  </Stepper>;
}

export function InvitationProgress({complete}: {complete:boolean}) {
  return <Stepper activeStep={complete?3:1} alternativeLabel sx={{my:3,"& .MuiStepLabel-label":{fontSize:11}}}>
    {["Invitation","Account setup","Ready to sign in"].map(label=><Step key={label}><StepLabel>{label}</StepLabel></Step>)}
  </Stepper>;
}
