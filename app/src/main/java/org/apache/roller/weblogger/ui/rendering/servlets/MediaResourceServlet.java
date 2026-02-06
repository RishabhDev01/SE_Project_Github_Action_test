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

        WeblogMediaResourceRequest resourceRequest = parseRequest(request);
        if (resourceRequest == null) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        MediaFile mediaFile = getMediaFile(resourceRequest);
        if (mediaFile == null) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        if (isNotModified(request, response, mediaFile, resourceRequest)) {
            return;
        }

        InputStream resourceStream = getInputStream(mediaFile, resourceRequest);
        if (resourceStream == null) {
            log.error("Unable to get input stream for media file");
            response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            return;
        }

        try {
            serveResource(response, resourceStream, mediaFile, resourceRequest);
        } catch (Exception ex) {
            log.error("ERROR", ex);
            if (!response.isCommitted()) {
                response.reset();
                response.sendError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            }
        } finally {
            // make sure stream to resource file is closed
            resourceStream.close();
        }
    }

    private WeblogMediaResourceRequest parseRequest(HttpServletRequest request) {
        try {
            WeblogMediaResourceRequest resourceRequest = new WeblogMediaResourceRequest(request);
            Weblog weblog = resourceRequest.getWeblog();
            if (weblog == null) {
                throw new WebloggerException("unable to lookup weblog: " + resourceRequest.getWeblogHandle());
            }
            return resourceRequest;
        } catch (Exception e) {
            log.debug("error creating weblog resource request", e);
            return null;
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

    private boolean isNotModified(HttpServletRequest request, HttpServletResponse response, MediaFile mediaFile, WeblogMediaResourceRequest resourceRequest) {
        long resourceLastMod = mediaFile.getLastModified();
        if (ModDateHeaderUtil.respondIfNotModified(request, response, resourceLastMod, resourceRequest.getDeviceType())) {
            return true;
        } else {
            ModDateHeaderUtil.setLastModifiedHeader(response, resourceLastMod, resourceRequest.getDeviceType());
            return false;
        }
    }

    private InputStream getInputStream(MediaFile mediaFile, WeblogMediaResourceRequest resourceRequest) {
        if (resourceRequest.isThumbnail()) {
            try {
                return mediaFile.getThumbnailInputStream();
            } catch (Exception e) {
                if (log.isDebugEnabled()) {
                    log.debug("ERROR loading thumbnail for " + mediaFile.getId(), e);
                } else {
                    log.warn("ERROR loading thumbnail for " + mediaFile.getId());
                }
                return null;
            }
        }
        return mediaFile.getInputStream();
    }

    private void serveResource(HttpServletResponse response, InputStream resourceStream, MediaFile mediaFile, WeblogMediaResourceRequest resourceRequest) throws IOException {
        if (resourceRequest.isThumbnail()) {
            response.setContentType("image/png");
        } else {
            response.setContentType(mediaFile.getContentType());
        }

        OutputStream out = response.getOutputStream();
        byte[] buf = new byte[RollerConstants.EIGHT_KB_IN_BYTES];
        int length;
        while ((length = resourceStream.read(buf)) > 0) {
            out.write(buf, 0, length);
        }
        out.close();
    }
}