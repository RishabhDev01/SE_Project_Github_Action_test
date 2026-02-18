/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 *  contributor license agreements.  The ASF licenses this file to You
 * under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.  For additional information regarding
 * copyright in this work, please see the NOTICE file in the top level
 * directory of this distribution.
 */

package org.apache.roller.weblogger.ui.rendering.servlets;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import javax.servlet.ServletConfig;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.apache.roller.util.RollerConstants;
import org.apache.roller.weblogger.WebloggerException;
import org.apache.roller.weblogger.business.MediaFileManager;
import org.apache.roller.weblogger.business.WebloggerFactory;
import org.apache.roller.weblogger.pojos.MediaFile;
import org.apache.roller.weblogger.pojos.Weblog;
import org.apache.roller.weblogger.ui.rendering.util.ModDateHeaderUtil;
import org.apache.roller.weblogger.ui.rendering.util.WeblogMediaResourceRequest;

/**
 * Serves media files uploaded by users.
 * 
 * Since we keep resources in a location outside of the webapp context we need a
 * way to serve them up. This servlet assumes that resources are stored on a
 * filesystem in the "uploads.dir" directory.
 */
public class MediaResourceServlet extends HttpServlet {

    private static Log log = LogFactory.getLog(MediaResourceServlet.class);

    @Override
    public void init(ServletConfig config) throws ServletException {
        super.init(config);
        log.info("Initializing ResourceServlet");
    }

    /**
     * Handles requests for user uploaded media file resources.
     */
    @Override
    public void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        try {
            WeblogMediaResourceRequest resourceRequest = parseRequest(request);
            Weblog weblog = resourceRequest.getWeblog();

            if (weblog == null) {
                throw new WebloggerException("unable to lookup weblog: "
                        + resourceRequest.getWeblogHandle());
            }

            MediaFile mediaFile = getMediaFile(resourceRequest);
            if (mediaFile == null) {
                response.sendError(HttpServletResponse.SC_NOT_FOUND);
                return;
            }

            if (isNotModified(request, response, mediaFile, resourceRequest)) {
                return;
            }

            serveMediaFile(response, mediaFile, resourceRequest);
        } catch (Exception e) {
            handleException(response, e);
        }
    }

    private WeblogMediaResourceRequest parseRequest(HttpServletRequest request) {
        try {
            return new WeblogMediaResourceRequest(request);
        } catch (Exception e) {
            log.debug("error creating weblog resource request", e);
            throw new RuntimeException(e);
        }
    }

    private MediaFile getMediaFile(WeblogMediaResourceRequest resourceRequest) {
        MediaFileManager mfMgr = WebloggerFactory.getWeblogger().getMediaFileManager();
        try {
            return mfMgr.getMediaFile(resourceRequest.getResourceId(), true);
        } catch (Exception ex) {
            log.debug("Unable to get resource", ex);
            return null;
        }
    }

    private boolean isNotModified(HttpServletRequest request, HttpServletResponse response, MediaFile mediaFile,
            WeblogMediaResourceRequest resourceRequest) {
        long resourceLastMod = mediaFile.getLastModified();
        if (ModDateHeaderUtil.respondIfNotModified(request, response, resourceLastMod,
                resourceRequest.getDeviceType())) {
            return true;
        } else {
            ModDateHeaderUtil.setLastModifiedHeader(response, resourceLastMod, resourceRequest.getDeviceType());
        }
        return false;
    }

    private void serveMediaFile(HttpServletResponse response, MediaFile mediaFile,
            WeblogMediaResourceRequest resourceRequest) {
        InputStream resourceStream = null;
        try {
            if (resourceRequest.isThumbnail()) {
                response.setContentType("image/png");
                resourceStream = mediaFile.getThumbnailInputStream();
            } else {
                response.setContentType(mediaFile.getContentType());
                resourceStream = mediaFile.getInputStream();
            }

            OutputStream out = response.getOutputStream();
            byte[] buf = new byte[RollerConstants.EIGHT_KB_IN_BYTES];
            int length;
            while ((length = resourceStream.read(buf)) > 0) {
                out.write(buf, 0, length);
            }
            out.close();
        } catch (Exception ex) {
            log.error("ERROR", ex);
            if (!response.isCommitted()) {
                response.reset();
                try {
                    response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
                } catch (IOException e) {
                    log.error("Error sending error response", e);
                }
            }
        } finally {
            if (resourceStream != null) {
                try {
                    resourceStream.close();
                } catch (IOException e) {
                    log.error("Error closing resource stream", e);
                }
            }
        }
    }

    private void handleException(HttpServletResponse response, Exception e) {
        log.debug("error creating weblog resource request", e);
        try {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
        } catch (IOException ex) {
            log.error("Error sending error response", ex);
        }
    }
}